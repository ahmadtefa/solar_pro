"""Short-lived, signed download and print tickets.

Browsers cannot attach ``Authorization`` headers to a plain ``<a href>`` or a
new window, so printing and file downloads need a URL the browser can open on
its own. Instead of weakening the API, the client asks for a **ticket**: a
short-lived JWT that names one exact artefact (a report, an entity export or a
printable document). Redeeming the ticket re-checks the caller's permissions
against the database, so a leaked URL expires quickly and can never escalate
privileges.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDeniedError, ValidationFailure
from app.core.security import create_access_token, decode_token
from app.models.identity import User

DOWNLOAD_TOKEN_TYPE = "download"  # noqa: S105 - JWT type marker, not a credential
TICKET_MINUTES = 10
ARTEFACT_KINDS = ("report", "entity", "document")


class DownloadService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id

    # ------------------------------------------------------------- ticketing
    def create_ticket(
        self,
        *,
        kind: str,
        code: str,
        file_format: str = "csv",
        parameters: dict[str, Any] | None = None,
        entity_id: str | None = None,
        base_url: str = "/api/v1/downloads",
    ) -> dict[str, Any]:
        if kind not in ARTEFACT_KINDS:
            raise ValidationFailure("Unknown download kind", supported=list(ARTEFACT_KINDS))
        if self.user_id is None:
            raise AuthenticationError("A signed-in user is required to create a download ticket")
        user = self.db.get(User, self.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("The account is no longer active")

        token, expires_at = create_access_token(
            user_id=user.id,
            company_id=self.company_id,
            session_id=None,
            password_hash=user.password_hash,
            permissions_version=int(user.permissions_version or 0),
            expires_delta=timedelta(minutes=TICKET_MINUTES),
            extra_claims={
                "typ": DOWNLOAD_TOKEN_TYPE,
                "dl": {
                    "kind": kind,
                    "code": code,
                    "format": file_format.lower(),
                    "parameters": parameters or {},
                    "entity_id": entity_id,
                },
            },
        )
        query = urlencode({"token": token})
        return {
            "kind": kind,
            "code": code,
            "file_format": file_format.lower(),
            "url": f"{base_url}?{query}",
            "token": token,
            "file_name": self.file_name_for(kind, code, file_format, parameters),
            "expires_at": expires_at.isoformat(),
            "expires_in_seconds": TICKET_MINUTES * 60,
        }

    def file_name_for(
        self, kind: str, code: str, file_format: str, parameters: dict[str, Any] | None = None
    ) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        extension = {"print": "html", "pdf": "pdf", "xlsx": "xlsx", "csv": "csv"}.get(file_format, file_format)
        parts = [kind, code.replace("/", "-")]
        numbers = parameters or {}
        if numbers.get("date_from") or numbers.get("date_to"):
            parts.append(f"{numbers.get('date_from', 'start')}_{numbers.get('date_to', 'end')}")
        parts.append(stamp)
        return f"{'-'.join(parts)}.{extension}"

    # -------------------------------------------------------------- redeeming
    def redeem(self, token: str) -> tuple[bytes, str, str]:
        """Return ``(content, file_name, media_type)`` for a ticket URL."""
        payload = decode_token(token, expected_type=DOWNLOAD_TOKEN_TYPE)
        ticket = payload.get("dl") or {}
        company_id = uuid.UUID(str(payload["cid"])) if payload.get("cid") else None
        user_id = uuid.UUID(str(payload["sub"]))
        if company_id is None:
            raise AuthenticationError("The download ticket has no company context")

        # Redeeming happens on a fresh session, so bind the identity from the
        # ticket before building any artefact.
        self.company_id = company_id
        self.user_id = user_id
        actor = _Actor(self.db, user_id, company_id)
        kind = ticket.get("kind")
        code = ticket.get("code")
        file_format = (ticket.get("format") or "csv").lower()
        parameters = ticket.get("parameters") or {}

        if kind == "report":
            actor.require_any("core.report.export", "core.report.view")
            return self._report_artefact(code, file_format, parameters)
        if kind == "entity":
            actor.require("core.import_job.export")
            return self._entity_artefact(code, file_format)
        if kind == "document":
            entity_id = ticket.get("entity_id")
            actor.require(f"{code}.print")
            return self._document_artefact(code, entity_id, file_format)
        raise ValidationFailure("Unknown download kind", supported=list(ARTEFACT_KINDS))

    # ------------------------------------------------------------- artefacts
    def _report_artefact(self, code: str, file_format: str, parameters: dict[str, Any]) -> tuple[bytes, str, str]:
        from app.api.exports import content_type_for
        from app.services.import_export_service import ImportExportService
        from app.services.report_service import ReportService

        result = ReportService(self.db, self.company_id).run(code, parameters)
        if file_format in {"print", "html"}:
            return result_html(result.to_dict()), f"{code}.html", "text/html; charset=utf-8"
        if file_format == "pdf":
            return result.to_pdf(), f"{code}.pdf", "application/pdf"
        payload = ImportExportService(self.db, self.company_id, user_id=self.user_id).export_report(
            code, parameters, file_format=file_format
        )
        return payload, f"{code}.{'xlsx' if file_format in {'xlsx', 'excel'} else 'csv'}", content_type_for(file_format)

    def _entity_artefact(self, entity_type: str, file_format: str) -> tuple[bytes, str, str]:
        from app.api.exports import content_type_for
        from app.services.import_export_service import ENTITY_DEFINITIONS, ImportExportService

        service = ImportExportService(self.db, self.company_id, user_id=self.user_id)
        rows = service.export_rows(entity_type)
        columns = list(ENTITY_DEFINITIONS[entity_type]["fields"]) if entity_type in ENTITY_DEFINITIONS else None
        if file_format in {"xlsx", "excel"}:
            data = service.to_xlsx_bytes(rows, columns, title=entity_type)
            return data, f"{entity_type}.xlsx", content_type_for("xlsx")
        if file_format in {"print", "html"}:
            return rows_html(entity_type, rows, columns), f"{entity_type}.html", "text/html; charset=utf-8"
        text = service.to_csv(rows, columns)
        return text.encode("utf-8-sig"), f"{entity_type}.csv", content_type_for("csv")

    def _document_artefact(self, entity_key: str, entity_id: str | None, file_format: str) -> tuple[bytes, str, str]:
        from app.api.documents import print_payload

        registry = document_registry()
        service_cls = registry.get(entity_key)
        if service_cls is None:
            raise ValidationFailure("Unknown printable document", supported=sorted(registry))
        if not entity_id:
            raise ValidationFailure("A document id is required for printing")
        document = self.db.get(service_cls.model, uuid.UUID(str(entity_id)))
        if document is None or getattr(document, "company_id", self.company_id) != self.company_id:
            raise ValidationFailure("The document was not found in this company")
        payload = print_payload(
            self.db,
            _Actor(self.db, self.user_id, self.company_id),
            document,
            service_cls.line_relationship,
        )
        title = payload.get("document", {}).get("document_no") or entity_key
        return document_html(payload, title), f"{title}.html", "text/html; charset=utf-8"


def document_registry() -> dict[str, Any]:
    """Map ``module.entity`` permission keys to their document service class.

    The registry is derived from the services themselves, so every document that
    exposes a print permission in the API is printable without a second list
    having to be maintained by hand.
    """
    import importlib
    import inspect
    import pkgutil

    import app.services as services_package
    from app.services.document_service import BaseDocumentService

    registry: dict[str, Any] = {}
    for info in pkgutil.iter_modules(services_package.__path__):
        module = importlib.import_module(f"app.services.{info.name}")
        for _, candidate in vars(module).items():
            if (
                inspect.isclass(candidate)
                and issubclass(candidate, BaseDocumentService)
                and candidate is not BaseDocumentService
                and candidate.__module__ == module.__name__
            ):
                registry[f"{candidate.permission_module}.{candidate.permission_entity}"] = candidate
    return registry


class _Actor:
    """Minimal permission context used when a request is authenticated by URL."""

    def __init__(self, db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> None:
        from app.services.auth_service import AuthService

        self.db = db
        self.user_id = user_id
        self.company_id = company_id
        self.user = db.get(User, user_id)
        if self.user is None or not self.user.is_active:
            raise AuthenticationError("The account is no longer active")
        self.permissions = AuthService(db).resolve_permissions(self.user, company_id)

    def require(self, code: str) -> None:
        if not self.permissions.has(code):
            raise PermissionDeniedError("You do not have permission to download this artefact", permission=code)

    def require_any(self, *codes: str) -> None:
        if not self.permissions.any_of(*codes):
            raise PermissionDeniedError("You do not have permission to download this artefact", permissions=list(codes))


# --------------------------------------------------------------------- HTML
_PRINT_CSS = """
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Tahoma, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 32px;
       color: #111827; background: #fff; }
html[dir="rtl"] body { direction: rtl; }
header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 3px solid #0f766e;
         padding-bottom: 16px; margin-bottom: 24px; }
h1 { font-size: 20px; margin: 0 0 4px; color: #0f766e; }
h2 { font-size: 15px; margin: 24px 0 8px; color: #374151; }
.meta { font-size: 12px; color: #4b5563; line-height: 1.6; }
.toolbar { position: sticky; top: 0; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
           padding: 10px 12px; margin-bottom: 20px; display: flex; gap: 10px; align-items: center; font-size: 12px; }
button { font: inherit; padding: 6px 14px; border-radius: 6px; border: 0; background: #0f766e; color: #fff;
         cursor: pointer; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: start; }
th { background: #f3f4f6; font-weight: 600; }
tbody tr:nth-child(even) { background: #fafafa; }
tfoot td { font-weight: 600; background: #f3f4f6; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px 24px; }
.kv { display: flex; justify-content: space-between; border-bottom: 1px dotted #d1d5db; padding: 4px 0; }
.totals { margin-top: 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }
.totals div { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; }
.signatures { margin-top: 48px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px; font-size: 12px; }
.signatures div { border-top: 1px solid #9ca3af; padding-top: 6px; }
@media print { .toolbar { display: none; } body { padding: 0; } }
"""


def _shell(title: str, body: str, *, rtl: bool = False) -> str:
    direction = "rtl" if rtl else "ltr"
    return f"""<!DOCTYPE html>
<html lang="{'ar' if rtl else 'en'}" dir="{direction}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_text(title)}</title>
<style>{_PRINT_CSS}</style>
</head>
<body>
<div class="toolbar">
  <button onclick="window.print()">{'طباعة' if rtl else 'Print'}</button>
  <button onclick="window.close()" style="background:#6b7280">{'إغلاق' if rtl else 'Close'}</button>
  <span>{'معاينة قابلة للطباعة' if rtl else 'Printable preview'}</span>
</div>
{body}
</body>
</html>"""


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return value


def _column_key(column: Any) -> str:
    if isinstance(column, dict):
        return str(column.get("key") or column.get("name") or "")
    return str(getattr(column, "key", None) or getattr(column, "name", None) or column)


def _column_label(column: Any) -> str:
    if isinstance(column, dict):
        return str(column.get("label") or column.get("title") or _column_key(column))
    return str(getattr(column, "label", None) or getattr(column, "title", None) or _column_key(column))


def _table(rows: list[dict[str, Any]], columns: list[str], totals: dict[str, Any] | None = None) -> str:
    head = "".join(f"<th>{_text(column)}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_text(_jsonable(row.get(column)))}</td>" for column in columns) + "</tr>"
        for row in rows
    )
    foot = ""
    if totals:
        cells = "".join(f"<td>{_text(_jsonable(totals.get(column)))}</td>" for column in columns)
        foot = f"<tfoot><tr>{cells}</tr></tfoot>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody>{foot}</table>"


def result_html(result: dict[str, Any]) -> str:
    columns = [_column_key(column) for column in result.get("columns") or []]
    rows = list(result.get("rows") or [])
    if not columns and rows:
        columns = list(rows[0].keys())
    labels = [_column_label(column) for column in result.get("columns") or []] or columns
    table = _table(rows, columns, result.get("totals"))
    table = table.replace(
        "".join(f"<th>{_text(column)}</th>" for column in columns),
        "".join(f"<th>{_text(label)}</th>" for label in labels),
        1,
    )
    meta = result.get("meta") or {}
    meta_rows = "".join(
        f'<div class="kv"><span>{_text(key)}</span><span>{_text(_jsonable(value))}</span></div>'
        for key, value in meta.items()
    )
    return _shell(
        str(result.get("title") or result.get("code") or "Report"),
        f"""<header>
  <div>
    <h1>{_text(result.get('title') or result.get('code'))}</h1>
    <div class="meta">Generated {_text(result.get('generated_at'))}</div>
  </div>
  <div class="meta">{meta_rows}</div>
</header>
<h2>Rows: {len(rows)}</h2>
{table}""",
    )


def rows_html(title: str, rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    columns = list(columns or (rows[0].keys() if rows else []))
    return _shell(title, f"<header><div><h1>{_text(title)}</h1></div></header>{_table(rows, columns)}")


def document_html(payload: dict[str, Any], title: str) -> str:
    company = payload.get("company") or {}
    document = payload.get("document") or {}
    lines = payload.get("lines") or []
    rtl = bool(company.get("name_ar")) and not company.get("name")
    header_fields = {key: value for key, value in document.items() if key not in {"lines", "created_at", "updated_at"}}
    cards = "".join(
        f'<div class="kv"><span>{_text(key)}</span><span>{_text(_jsonable(value))}</span></div>'
        for key, value in header_fields.items()
    )
    columns = list(lines[0].keys()) if lines else []
    table = _table(lines, columns) if columns else "<p>No lines</p>"
    return _shell(
        title,
        f"""<header>
  <div>
    <h1>{_text(company.get('name_ar') or company.get('name') or 'Kayan ERP')}</h1>
    <div class="meta">
      {_text(company.get('tax_registration_number') or '')}<br />
      {_text(company.get('phone') or '')} {_text(company.get('email') or '')}<br />
      {_text(company.get('website') or '')}
    </div>
  </div>
  <div class="meta" style="text-align:end">
    <strong>{_text(document.get('document_no') or title)}</strong><br />
    {_text(payload.get('generated_at'))}<br />
    {_text(payload.get('generated_by'))}
  </div>
</header>
<h2>Details</h2>
<div class="grid">{cards}</div>
<h2>Lines</h2>
{table}
<div class="signatures">
  <div>Prepared by</div>
  <div>Approved by</div>
  <div>Received by</div>
</div>""",
        rtl=rtl,
    )


__all__ = [
    "ARTEFACT_KINDS",
    "DOWNLOAD_TOKEN_TYPE",
    "DownloadService",
    "document_html",
    "document_registry",
    "result_html",
    "rows_html",
]
