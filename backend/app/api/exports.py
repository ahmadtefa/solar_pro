"""Small helpers for returning generated files (CSV, Excel, PDF) from the API."""

from __future__ import annotations

from typing import Any

from fastapi import Response

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"

MEDIA_TYPES = {"csv": CSV_MEDIA_TYPE, "xlsx": XLSX_MEDIA_TYPE, "pdf": PDF_MEDIA_TYPE}


def content_type_for(file_format: str) -> str:
    return MEDIA_TYPES.get(file_format.lower(), "application/octet-stream")


def binary_response(data: bytes, file_name: str, media_type: str) -> Response:
    """Return raw bytes with a download filename.

    Uses ``latin-1`` for the legacy header and adds the RFC 5987 ``filename*``
    parameter so non-ASCII document numbers survive the round trip.
    """
    from urllib.parse import quote

    safe_name = file_name.encode("ascii", "ignore").decode() or "export"
    disposition = (
        f'attachment; filename="{safe_name}"; '
        f"filename*=UTF-8''{quote(file_name, safe='')}"
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


def export_response(data: bytes | str, file_name: str, file_format: str) -> Response:
    if isinstance(data, str):
        data = data.encode("utf-8-sig")
    return binary_response(data, file_name, content_type_for(file_format))


def with_extension(name: str, file_format: str) -> str:
    """``doc_no`` + ``csv`` -> ``doc_no.csv`` with path separators removed."""
    cleaned = str(name).strip().replace("/", "-") or "export"
    extension = f".{file_format.lower()}"
    return cleaned if cleaned.lower().endswith(extension) else cleaned + extension


def html_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Render rows as a minimal printable HTML table (used for print endpoints)."""
    columns = columns or (list(rows[0].keys()) if rows else [])
    head = "".join(f"<th>{_escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_escape(row.get(column))}</td>" for column in columns) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
