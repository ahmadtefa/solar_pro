"""Generic HTTP surface for business documents.

Every transactional document (quotation, purchase order, invoice, journal entry,
production order, ...) inherits the same lifecycle from
:class:`~app.services.document_service.BaseDocumentService`.  This factory turns
that contract into REST endpoints once, so each router only declares which
service it exposes and which extra endpoints it needs.  No business rule lives
here: permissions are checked against the service's declared entity, and every
state change is delegated to the service.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request, status
from sqlalchemy import func, or_, select

from app.api.crud import serialise
from app.api.deps import DB, CurrentUser, CurrentUserDep, audit_context
from app.core.coercion import normalise_payload
from app.core.enums import DocumentStatus
from app.core.errors import ValidationFailure
from app.core.pagination import PageParams
from app.services.document_service import BaseDocumentService


@dataclass
class DocumentSpec:
    """Declares one document resource for :func:`build_document_router`."""

    name: str
    service: type[BaseDocumentService]
    label: str
    tag: str
    date_field: str = "document_date"
    party_field: str | None = None
    reference_field: str | None = None
    search_fields: Sequence[str] = ("document_no", "reference")
    status_values: Sequence[str] | None = None
    lines_key: str | None = None
    create_only: bool = False
    extra_routes: Callable[[APIRouter], None] | None = None
    extra_actions: dict[str, str] = field(default_factory=dict)  # url -> method name


def build_document_router(spec: DocumentSpec) -> APIRouter:
    """Create the standard lifecycle endpoints for a document service."""
    router = APIRouter(tags=[spec.tag])
    service_cls = spec.service
    model = service_cls.model
    lines_key = spec.lines_key or service_cls.line_relationship

    def permission(action: str) -> str:
        return f"{service_cls.permission_module}.{service_cls.permission_entity}.{action}"

    def make_service(db: DB, current: CurrentUserDep, request: Request) -> BaseDocumentService:
        context = audit_context(current, request)
        context.branch_id = getattr(current.session, "branch_id", None)
        return service_cls(db, current.company_id, user_id=current.id, audit_context=context)

    def load(service: BaseDocumentService, document_id: uuid.UUID) -> Any:
        return service.get_document(document_id)

    def detail(document: Any) -> dict[str, Any]:
        payload = serialise(document)
        lines = getattr(document, lines_key, None) or []
        payload["lines"] = [serialise(line) for line in lines]
        payload["line_count"] = len(payload["lines"])
        if hasattr(document, "journal_entry_id"):
            payload["journal_entry_id"] = str(document.journal_entry_id) if document.journal_entry_id else None
        return payload

    # ------------------------------------------------------------------ list
    @router.get("", summary=f"List {spec.label}")
    def list_documents(
        request: Request,
        db: DB,
        current: CurrentUserDep,
        params: PageParams = Depends(),
        status_filter: str | None = Query(None, alias="status"),
        date_from: str | None = None,
        date_to: str | None = None,
        party_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        open_only: bool = False,
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        current.require(permission("view"))
        stmt = select(model).where(model.company_id == current.company_id)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        if status_filter:
            stmt = stmt.where(model.status.in_([item.strip() for item in status_filter.split(",")]))
        if open_only and hasattr(model, "balance_amount"):
            stmt = stmt.where(model.balance_amount > 0)
        date_column = getattr(model, spec.date_field, None)
        if date_column is not None:
            if date_from:
                stmt = stmt.where(date_column >= date_from)
            if date_to:
                stmt = stmt.where(date_column <= date_to)
        if party_id is not None and spec.party_field:
            stmt = stmt.where(getattr(model, spec.party_field) == party_id)
        if branch_id is not None and hasattr(model, "branch_id"):
            stmt = stmt.where(model.branch_id == branch_id)
        if params.q:
            conditions = [
                getattr(model, column_name).ilike(f"%{params.q}%")
                for column_name in spec.search_fields
                if hasattr(model, column_name)
            ]
            if conditions:
                stmt = stmt.where(or_(*conditions))
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        ordering = [date_column.desc()] if date_column is not None else []
        stmt = stmt.order_by(*ordering, model.created_at.desc())
        rows = db.execute(stmt.offset(params.offset).limit(min(params.limit, limit))).scalars().unique().all()
        return {
            "items": [serialise(row) for row in rows],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "pages": (total + params.page_size - 1) // params.page_size if params.page_size else 0,
        }

    # ---------------------------------------------------------------- detail
    @router.get("/{document_id}", summary=f"Read one {spec.label}")
    def get_document(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
        current.require(permission("view"))
        return detail(load(make_service(db, current, request), document_id))

    # ---------------------------------------------------------------- create
    @router.post("", status_code=status.HTTP_201_CREATED, summary=f"Create {spec.label}")
    def create_document(
        request: Request,
        db: DB,
        current: CurrentUserDep,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        current.require(permission("create"))
        service = make_service(db, current, request)
        body = dict(normalise_payload(dict(payload)))
        keywords = {
            name
            for name, parameter in inspect.signature(service.create).parameters.items()
            if name != "payload" and parameter.kind in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}
        }
        kwargs = {name: body.pop(name) for name in list(body) if name in keywords}
        document = service.create(body, **kwargs)
        db.flush()
        return detail(document)

    if not spec.create_only:
        # ------------------------------------------------------------ update
        @router.patch("/{document_id}", summary=f"Edit a draft {spec.label}")
        def update_document(
            document_id: uuid.UUID,
            request: Request,
            db: DB,
            current: CurrentUserDep,
            payload: dict[str, Any] = Body(...),
        ) -> dict[str, Any]:
            current.require(permission("edit"))
            service = make_service(db, current, request)
            document = load(service, document_id)
            service.update(document, normalise_payload(dict(payload)))
            db.flush()
            return detail(document)

        # ------------------------------------------------------------ delete
        @router.delete("/{document_id}", summary=f"Delete a draft {spec.label}")
        def delete_document(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
            current.require(permission("delete"))
            service = make_service(db, current, request)
            document = load(service, document_id)
            service.delete_draft(document)
            return {"id": str(document_id), "deleted": True}

        # -------------------------------------------------------- transitions
        def _transition(action: str, method: str, *, needs_reason: bool = False, allow_draft: bool = False):
            @router.post(f"/{{document_id}}/{action}", name=f"{spec.name}_{action}", summary=f"{action.title()} {spec.label}")
            def handler(
                document_id: uuid.UUID,
                request: Request,
                db: DB,
                current: CurrentUserDep,
                payload: dict[str, Any] = Body(default={}),
            ) -> dict[str, Any]:
                current.require(permission("edit" if action == "submit" else action))
                service = make_service(db, current, request)
                document = load(service, document_id)
                target = getattr(service, method)
                keyword = "allow_draft" if allow_draft else ("reason" if needs_reason else None)
                if keyword == "reason" and not payload.get("reason"):
                    raise ValidationFailure(f"A reason is required to {action} this document")
                document = target(document, **({keyword: payload.get(keyword) if keyword == "reason" else True} if keyword else {}))
                db.flush()
                return detail(document)

            return handler

        def submit_handler() -> None:
            @router.post("/{document_id}/submit", summary=f"Submit {spec.label}")
            def handler(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
                current.require(permission("edit"))
                service = make_service(db, current, request)
                document = service.submit(load(service, document_id))
                db.flush()
                return detail(document)

        def approve_handler() -> None:
            @router.post("/{document_id}/approve", summary=f"Approve {spec.label}")
            def handler(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
                current.require(permission("approve"))
                service = make_service(db, current, request)
                document = load(service, document_id)
                _run_workflow(service, document, "approve")
                document = service.approve(document)
                db.flush()
                return detail(document)

        def reject_handler() -> None:
            @router.post("/{document_id}/reject", summary=f"Reject {spec.label}")
            def handler(
                document_id: uuid.UUID,
                request: Request,
                db: DB,
                current: CurrentUserDep,
                payload: dict[str, Any] = Body(...),
            ) -> dict[str, Any]:
                current.require(permission("reject"))
                if not payload.get("reason"):
                    raise ValidationFailure("A rejection reason is required")
                service = make_service(db, current, request)
                document = load(service, document_id)
                _run_workflow(service, document, "reject", payload.get("reason"))
                document = service.reject(document, reason=payload["reason"])
                db.flush()
                return detail(document)

        def post_handler() -> None:
            @router.post("/{document_id}/post", summary=f"Post {spec.label}")
            def handler(
                document_id: uuid.UUID,
                request: Request,
                db: DB,
                current: CurrentUserDep,
                payload: dict[str, Any] = Body(default={}),
            ) -> dict[str, Any]:
                current.require(permission("post"))
                service = make_service(db, current, request)
                document = service.post(load(service, document_id), allow_draft=bool(payload.get("allow_draft")))
                db.flush()
                return detail(document)

        def unpost_handler() -> None:
            @router.post("/{document_id}/unpost", summary=f"Unpost {spec.label} (reversal)")
            def handler(
                document_id: uuid.UUID,
                request: Request,
                db: DB,
                current: CurrentUserDep,
                payload: dict[str, Any] = Body(default={}),
            ) -> dict[str, Any]:
                current.require(permission("unpost"))
                service = make_service(db, current, request)
                document = service.unpost(
                    load(service, document_id), reason=payload.get("reason") or "Correction"
                )
                db.flush()
                return detail(document)

        def cancel_handler() -> None:
            @router.post("/{document_id}/cancel", summary=f"Cancel {spec.label}")
            def handler(
                document_id: uuid.UUID,
                request: Request,
                db: DB,
                current: CurrentUserDep,
                payload: dict[str, Any] = Body(...),
            ) -> dict[str, Any]:
                current.require(permission("cancel"))
                if not payload.get("reason"):
                    raise ValidationFailure("A cancellation reason is required")
                service = make_service(db, current, request)
                document = service.cancel(load(service, document_id), reason=payload["reason"])
                db.flush()
                return detail(document)

        submit_handler()
        approve_handler()
        reject_handler()
        post_handler()
        unpost_handler()
        cancel_handler()

        # -------------------------------------------------------- print/timeline
        @router.get("/{document_id}/print", summary=f"Printable payload for {spec.label}")
        def print_document(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
            current.require(permission("print"))
            service = make_service(db, current, request)
            document = load(service, document_id)
            return print_payload(db, current, document, lines_key)

        @router.get("/{document_id}/timeline", summary=f"Audit timeline of {spec.label}")
        def timeline(document_id: uuid.UUID, request: Request, db: DB, current: CurrentUserDep) -> dict[str, Any]:
            current.require(permission("view"))
            from app.models.identity import AuditLog

            rows = db.execute(
                select(AuditLog)
                .where(AuditLog.company_id == current.company_id, AuditLog.entity_id == document_id)
                .order_by(AuditLog.created_at)
            ).scalars().all()
            return {
                "items": [
                    {
                        "at": row.created_at.isoformat() if row.created_at else None,
                        "action": row.action,
                        "actor": row.user_email,
                        "remarks": row.remarks,
                        "changes": row.new_values,
                    }
                    for row in rows
                ]
            }

    for url, method_name in spec.extra_actions.items():
        method = getattr(service_cls, method_name, None)
        if method is None:
            continue
        _register_action(router, spec, url, method, permission)

    if spec.extra_routes is not None:
        spec.extra_routes(router)

    return router


def _register_action(
    router: APIRouter,
    spec: DocumentSpec,
    url: str,
    method: Callable[..., Any],
    permission: Callable[[str], str],
) -> None:
    """Expose a service method (``create_invoice``, ``issue_materials`` ...) over HTTP.

    The body of the request is passed to the method: named fields become keyword
    arguments, and any leftover payload is handed to the method's document-level
    payload parameter.  Methods that return plain dictionaries are returned as
    is, mapped objects are serialised together with their lines.
    """
    parameters = list(inspect.signature(method).parameters.values())[1:]  # drop self

    def handler(
        request: Request,
        db: DB,
        current: CurrentUserDep,
        document_id: uuid.UUID | None = None,
        payload: dict[str, Any] = Body(default={}),
    ) -> dict[str, Any]:
        current.require(permission("create"))
        body = dict(payload or {})
        service = spec.service(
            db, current.company_id, user_id=current.id, audit_context=audit_context(current, request)
        )
        positional: list[Any] = []
        keywords: dict[str, Any] = {}
        pending_payload = True
        for parameter in parameters:
            name = parameter.name
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                if name in body:
                    keywords[name] = body.pop(name)
                else:
                    keywords[name] = body.pop(name, parameter.default)
                continue
            if positional == [] and document_id is not None and name in {
                "document_id",
                "order_id",
                "request_id",
                "invoice_id",
                "quotation_id",
                "project_id",
                "asset_id",
                "run_id",
                "claim_id",
                "expense_id",
                "advance_id",
                "contract_id",
                "work_order_id",
                "rfq_id",
                "ticket_id",
                "milestone_id",
                "budget_id",
                "timesheet_id",
            }:
                positional.append(document_id)
                continue
            if name in body and parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and pending_payload:
                keywords[name] = body.pop(name)
                continue
            if pending_payload:
                positional.append(body)
                pending_payload = False
                continue
            positional.append(parameter.default)
        result = method(service, *positional, **keywords)
        db.flush()
        if isinstance(result, dict):
            return result
        data = serialise(result)
        lines = getattr(result, spec.service.line_relationship, None) or []
        data["lines"] = [serialise(line) for line in lines]
        return data

    method_map: dict[str, str] = {}
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            method_map[parameter.name] = "query"
        elif parameter.name in body_parameters:
            method_map[parameter.name] = "query"
    if str(getattr(method, "__http_method__", "")).upper() == "GET":
        method_map = dict.fromkeys(method_map, "query")
    _register_route(router, f"/{{document_id}}/{url}", handler, method_map)


#: Parameter names that are read from the query string instead of the body.
body_parameters: set[str] = {"payload", "payload_json", "body"}


def _register_route(router: APIRouter, path: str, handler: Callable[..., Any], query_map: dict[str, str]) -> None:
    router.add_api_route(path, handler, methods=["POST"], summary=path.rsplit("/", 1)[-1].replace("_", " "))


def _run_workflow(service: BaseDocumentService, document: Any, action: str, remarks: str | None = None) -> None:
    """Feed an approval decision to the workflow engine when the document has one."""
    from app.models.workflow import WorkflowInstance
    from app.services.workflow_service import WorkflowService

    instance = service.db.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.company_id == service.company_id,
            WorkflowInstance.document_type == service.document_type,
            WorkflowInstance.document_id == document.id,
            WorkflowInstance.status.in_(["pending", "in_progress"]),
        )
    ).scalars().first()
    if instance is None:
        return
    workflow = WorkflowService(service.db, service.company_id, user_id=service.user_id)
    workflow.decide(instance, action=action, user_id=service.user_id, comments=remarks)


def print_payload(db: DB, current: CurrentUser, document: Any, lines_key: str) -> dict[str, Any]:
    """Company letterhead + document header + lines, ready for PDF rendering."""
    from app.models.platform import Company

    company = db.get(Company, current.company_id)
    lines = getattr(document, lines_key, None) or []
    return {
        "company": serialise(company, ["id", "code", "name", "name_ar", "logo_url", "tax_registration_number", "phone", "email", "website"]),
        "document": serialise(document),
        "lines": [serialise(line) for line in lines],
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "generated_by": current.user.email,
        "statuses": [item.value for item in DocumentStatus],
    }


def document_number_filter(model: Any, value: str) -> Any:
    return model.document_no.ilike(f"%{value}%")


__all__ = ["DocumentSpec", "build_document_router", "print_payload"]
