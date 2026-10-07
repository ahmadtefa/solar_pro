"""Attachment and document management: secure upload, listing and download."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailure
from app.models.identity import Attachment
from app.services.attachment_service import DANGEROUS_EXTENSIONS, AttachmentService
from app.services.audit_service import AuditService

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.get("", summary="List attachments of an entity")
def list_attachments(
    db: DB,
    current: CurrentUserDep,
    entity_type: str = Query(...),
    entity_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    current.require("core.attachment.view")
    rows = AttachmentService(db, current.company_id, user_id=current.id).list_for_entity(entity_type, entity_id)
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("", status_code=201, summary="Upload one or more files against an entity")
async def upload(
    db: DB,
    current: CurrentUserDep,
    entity_type: str = Form(...),
    entity_id: uuid.UUID = Form(...),
    files: list[UploadFile] = File(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
    category: str | None = Form(None),
    is_public: bool = Form(False),
) -> dict[str, Any]:
    current.require("core.attachment.create")
    if not files:
        raise ValidationFailure("At least one file is required")
    service = AttachmentService(db, current.company_id, user_id=current.id)
    created = []
    for upload_file in files:
        content = await upload_file.read()
        if not content:
            raise ValidationFailure(f"{upload_file.filename} is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationFailure(f"{upload_file.filename} exceeds the 25 MB upload limit")
        import io

        attachment = service.upload(
            entity_type=entity_type,
            entity_id=entity_id,
            file_name=upload_file.filename or "upload.bin",
            stream=io.BytesIO(content),
            content_type=upload_file.content_type,
            title=title,
            description=description,
            category=category,
        )
        if is_public:
            attachment.is_public = True
        db.flush()
        AuditService(db, audit_context(current)).log_create(
            attachment, entity_type="attachment", label=attachment.file_name
        )
        created.append(serialise(attachment))
    return {"items": created, "total": len(created)}


@router.get("/{attachment_id}", summary="Attachment metadata")
def get_attachment(attachment_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.attachment.view")
    attachment = AttachmentService(db, current.company_id, user_id=current.id).get(attachment_id)
    return serialise(attachment)


@router.get("/{attachment_id}/download", summary="Download or preview a file")
def download(
    attachment_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    inline: bool = False,
) -> FileResponse:
    current.require("core.attachment.view")
    service = AttachmentService(db, current.company_id, user_id=current.id)
    attachment = service.get(attachment_id)
    if not attachment.is_public and attachment.uploaded_by_id != current.id:
        if not current.can("core.attachment.export") and not current.can("core.attachment.edit"):
            raise PermissionDeniedError("This attachment is private")
    path = service.file_path(attachment)
    if not path.exists():
        raise NotFoundError("The stored file is missing", id=str(attachment_id))
    service.register_download(attachment)
    db.flush()
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=None if inline else attachment.original_file_name or attachment.file_name,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.delete("/{attachment_id}", summary="Delete an attachment")
def delete_attachment(
    attachment_id: uuid.UUID, db: DB, current: CurrentUserDep, hard: bool = False
) -> dict[str, Any]:
    current.require("core.attachment.delete")
    service = AttachmentService(db, current.company_id, user_id=current.id)
    attachment = service.get(attachment_id)
    service.delete(attachment_id, hard=hard)
    db.flush()
    return {"id": str(attachment_id), "file_name": attachment.file_name, "deleted": True}


@router.get("/counts/{entity_type}", summary="Attachment counters for a set of records")
def counts(
    entity_type: str,
    db: DB,
    current: CurrentUserDep,
    entity_ids: str = Query(..., description="Comma-separated UUID list"),
) -> dict[str, Any]:
    current.require("core.attachment.view")
    ids = [uuid.UUID(part) for part in entity_ids.split(",") if part.strip()]
    counts_map = AttachmentService(db, current.company_id, user_id=current.id).entity_counts(entity_type, ids)
    return {"counts": {str(key): value for key, value in counts_map.items()}}


@router.get("/counters/{entity_type}/{entity_id}", summary="Counters by category for one record")
def counters(entity_type: str, entity_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.attachment.view")
    return AttachmentService(db, current.company_id, user_id=current.id).counters_for(entity_type, entity_id)


@router.get("/types/allowed", summary="Accepted file extensions")
def allowed_types(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.attachment.view")
    from app.core.config import settings

    extensions = sorted(set(settings.allowed_extensions) - DANGEROUS_EXTENSIONS)
    return {"extensions": extensions, "blocked": sorted(DANGEROUS_EXTENSIONS)}


@router.get("/expiring", summary="Documents whose expiry is approaching")
def expiring(
    db: DB,
    current: CurrentUserDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("core.attachment.view")
    service = AttachmentService(db, current.company_id, user_id=current.id)
    result = getattr(service, "expiring_documents", None)
    if callable(result):
        return {"items": result(days=days, limit=limit)}
    return {"items": [], "total": 0, "note": "No expiry tracking configured"}


def _attachment_model() -> type[Attachment]:
    return Attachment


__all__ = ["router"]
