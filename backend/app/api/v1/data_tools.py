"""Import/export and backup tools (administrator surface)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, Query, Response, UploadFile

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.exports import export_response, with_extension
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailure
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.import_export_service import ImportExportService

router = APIRouter()

MAX_IMPORT_BYTES = 20 * 1024 * 1024

# --------------------------------------------------------------------------- #
# Import: template -> upload -> map -> validate -> preview -> commit
# --------------------------------------------------------------------------- #
@router.get("/import/entities", summary="Entities that can be imported")
def import_entities(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.import_job.view")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    items = service.available_entities()
    return {"items": items, "total": len(items)}


@router.get("/import/template/{entity_type}", summary="Download a CSV template for an entity")
def import_template(
    entity_type: str,
    db: DB,
    current: CurrentUserDep,
    sample: bool = True,
    file_format: str = Query("csv", pattern="^(csv|xlsx)$"),
) -> Response:
    current.require("core.import_job.view")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    rows = service.template_rows(entity_type, sample=sample)
    if file_format == "xlsx":
        data: bytes | str = service.to_xlsx_bytes(rows, title=f"{entity_type} template")
    else:
        data = service.to_csv(rows)
    return export_response(data, with_extension(f"template-{entity_type}", file_format), file_format)


@router.post("/import/upload", status_code=201, summary="Upload a CSV/Excel file and create an import job")
async def import_upload(
    db: DB,
    current: CurrentUserDep,
    entity_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    column_mapping: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    current.require("core.import_job.create")
    content = await file.read()
    if not content:
        raise ValidationFailure("The uploaded file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise ValidationFailure("The uploaded file exceeds the 20 MB import limit")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    rows = service.read_tabular(content, file.filename or "upload.csv")
    if not rows:
        raise ValidationFailure("No data rows were found in the uploaded file")
    mapping = None
    if column_mapping:
        import json

        try:
            mapping = json.loads(column_mapping)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValidationFailure("column_mapping must be valid JSON") from exc
    job = service.create_job(
        entity_type,
        rows=rows,
        file_name=file.filename,
        column_mapping=mapping,
    )
    db.flush()
    AuditService(db, audit_context(current)).log_create(job, entity_type="import_job", label=str(job.id))
    return {
        **serialise(job),
        "row_count": len(rows),
        "columns": sorted({key for row in rows for key in row}),
        "next": f"/api/v1/data-tools/import/jobs/{job.id}/validate",
    }


@router.post("/import/rows", status_code=201, summary="Create an import job from JSON rows")
def import_rows(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.import_job.create")
    entity_type = payload.get("entity_type")
    rows = payload.get("rows")
    if not entity_type or not isinstance(rows, list) or not rows:
        raise ValidationFailure("entity_type and a non-empty rows array are required")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    job = service.create_job(
        entity_type,
        rows=rows,
        file_name=payload.get("file_name"),
        column_mapping=payload.get("column_mapping"),
    )
    db.flush()
    return {**serialise(job), "row_count": len(rows)}


@router.get("/import/jobs", summary="Import jobs")
def import_jobs(
    db: DB, current: CurrentUserDep, status_filter: str | None = Query(None, alias="status"), limit: int = 100
) -> dict[str, Any]:
    current.require("core.import_job.view")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    rows = service.list_jobs(limit=limit)
    if status_filter:
        rows = [row for row in rows if getattr(row, "status", None) == status_filter]
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/import/jobs/{job_id}", summary="Import job with its rows")
def import_job(job_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.import_job.view")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    job = service.job(job_id)
    preview = service.preview(job_id, limit=200)
    return {**serialise(job), "preview": preview}


@router.post("/import/jobs/{job_id}/validate", summary="Validate every row and report invalid ones")
def import_validate(job_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.import_job.create")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    result = service.validate(job_id)
    db.flush()
    return result


@router.get("/import/jobs/{job_id}/preview", summary="Preview how rows will be stored")
def import_preview(
    job_id: uuid.UUID, db: DB, current: CurrentUserDep, limit: int = Query(100, ge=1, le=1000)
) -> dict[str, Any]:
    current.require("core.import_job.view")
    return ImportExportService(db, current.company_id, user_id=current.id).preview(job_id, limit=limit)


@router.post("/import/jobs/{job_id}/commit", summary="Import the valid rows")
def import_commit(
    job_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("core.import_job.create")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    result = service.commit(job_id, skip_invalid=bool(payload.get("skip_invalid", True)))
    db.flush()
    AuditService(db, audit_context(current)).log(
        "import_committed",
        entity_type="import_job",
        entity_id=job_id,
        label=str(result.get("entity_type") or ""),
        new_values={key: value for key, value in result.items() if key in {"imported", "skipped", "failed"}},
    )
    return result


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
@router.get("/export/entities", summary="Entities that can be exported")
def export_entities(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.import_job.export")
    items = ImportExportService(db, current.company_id, user_id=current.id).available_entities()
    return {"items": items, "total": len(items)}


@router.post("/export/{entity_type}", summary="Export master data or documents to CSV/Excel")
def export_entity(
    entity_type: str,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
    file_format: str = Query("csv", pattern="^(csv|xlsx)$"),
    limit: int = Query(5000, ge=1, le=50000),
) -> Response:
    current.require("core.import_job.export")
    service = ImportExportService(db, current.company_id, user_id=current.id)
    rows = service.export_rows(entity_type, filters=payload.get("filters") or {}, limit=limit)
    columns = payload.get("columns") or None
    if file_format == "xlsx":
        data: bytes | str = service.to_xlsx_bytes(rows, columns=columns, title=entity_type)
    else:
        data = service.to_csv(rows, columns=columns)
    return export_response(data, with_extension(entity_type, file_format), file_format)


# --------------------------------------------------------------------------- #
# Backup and restore
# --------------------------------------------------------------------------- #
@router.get("/backup", summary="Backup history")
def list_backups(db: DB, current: CurrentUserDep, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    current.require("core.backup.view")
    service = BackupService(db, current.company_id, user_id=current.id)
    rows = service.list_backups(limit=limit)
    return {
        "items": [serialise(row) for row in rows],
        "total": len(rows),
        "directory": str(service.backup_directory()),
        "schedule": service.schedule_settings(),
    }


@router.post("/backup", status_code=201, summary="Create a backup now")
def create_backup(db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    current.require("core.backup.create")
    service = BackupService(db, current.company_id, user_id=current.id)
    job = service.create_backup(
        backup_type=payload.get("backup_type") or "manual",
        scope=payload.get("scope") or "full",
        notes=payload.get("notes"),
    )
    db.flush()
    AuditService(db, audit_context(current)).log_create(job, entity_type="backup_job", label=str(job.id))
    return serialise(job)


@router.get("/backup/{backup_id}", summary="Backup detail")
def get_backup(backup_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.backup.view")
    service = BackupService(db, current.company_id, user_id=current.id)
    return serialise(service.get(backup_id))


@router.post("/backup/{backup_id}/verify", summary="Verify a backup archive")
def verify_backup(backup_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.backup.view")
    service = BackupService(db, current.company_id, user_id=current.id)
    return service.verify(backup_id)


@router.get("/backup/{backup_id}/restore-instructions", summary="How to restore this backup")
def restore_instructions(backup_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.backup.view")
    service = BackupService(db, current.company_id, user_id=current.id)
    return service.restore_instructions(backup_id)


@router.delete("/backup/{backup_id}", summary="Delete a backup archive")
def delete_backup(backup_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.backup.delete")
    from app.services.backup_service import BackupJob  # noqa: F401  (documentation import)

    service = BackupService(db, current.company_id, user_id=current.id)
    job = service.get(backup_id)
    path = service.backup_directory() / (job.file_name or "")
    if job.file_name and path.exists():
        path.unlink()
    service.db.delete(job)
    service.db.flush()
    AuditService(db, audit_context(current)).log(
        "backup_deleted", entity_type="backup_job", entity_id=backup_id, label=job.file_name
    )
    return {"id": str(backup_id), "deleted": True}


@router.post("/backup/prune", summary="Keep only the newest N backups")
def prune_backups(db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    current.require("core.backup.delete")
    keep = int(payload.get("keep") or 14)
    if keep < 1:
        raise ValidationFailure("keep must be at least 1")
    result = BackupService(db, current.company_id, user_id=current.id).prune(keep=keep)
    db.flush()
    return result


@router.post("/backup/run-scheduled", summary="Run the scheduled backup if due")
def run_scheduled(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    if not current.is_superuser:
        raise PermissionDeniedError("Scheduled backups can only be triggered by an operator")
    result = BackupService(db, current.company_id, user_id=current.id).run_scheduled()
    db.flush()
    return result


@router.get("/backup/{backup_id}/download", summary="Download a backup archive")
def download_backup(backup_id: uuid.UUID, db: DB, current: CurrentUserDep) -> Response:
    current.require("core.backup.view")
    from fastapi.responses import FileResponse

    service = BackupService(db, current.company_id, user_id=current.id)
    job = service.get(backup_id)
    path = service.backup_directory() / (job.file_name or "")
    if not job.file_name or not path.exists():
        raise NotFoundError("The backup archive is missing", id=str(backup_id))
    return FileResponse(path, media_type="application/zip", filename=job.file_name)


__all__ = ["router"]
