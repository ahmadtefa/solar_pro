"""Signed download and print URLs.

The Flutter client (and any browser) can open these URLs directly: the ticket
carries the caller's identity for ten minutes and every redemption re-checks
permissions in the database.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Query, Request, Response

from app.api.deps import DB, CurrentUserDep
from app.services.download_service import ARTEFACT_KINDS, DownloadService

router = APIRouter(tags=["downloads"])


@router.post("/tickets", summary="Create a short-lived download or print ticket")
def create_ticket(
    request: Request,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    kind = str(payload.get("kind") or "report")
    if kind not in ARTEFACT_KINDS:
        kind = "report"
    code = str(payload.get("code") or "")
    if not code:
        from app.core.errors import ValidationFailure

        raise ValidationFailure("A report code, entity type or document type is required")

    # Creation is a normal authenticated request, so it checks permissions with
    # the same middleware as every other endpoint.
    if kind == "report":
        current.require("core.report.export")
    elif kind == "entity":
        current.require("core.import_job.export")
    else:
        current.require(f"{code}.print")

    base_url = str(request.base_url).rstrip("/") + "/api/v1/downloads"
    service = DownloadService(db, current.company_id, user_id=current.id)
    ticket = service.create_ticket(
        kind=kind,
        code=code,
        file_format=str(payload.get("file_format") or "csv"),
        parameters=payload.get("parameters") or {},
        entity_id=payload.get("entity_id"),
        base_url=base_url,
    )
    ticket["expires_at"] = ticket["expires_at"]
    return ticket


@router.get("", summary="Redeem a download ticket (browser friendly, no header needed)")
def redeem(token: str = Query(..., description="Ticket issued by POST /downloads/tickets")) -> Response:
    from app.api.exports import binary_response
    from app.core.database import session_scope

    with session_scope() as db:
        service = DownloadService(db, uuid.UUID(int=0))
        content, file_name, media_type = service.redeem(token)
    return binary_response(content, file_name, media_type)


__all__ = ["router"]
