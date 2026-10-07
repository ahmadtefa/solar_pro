"""Reusable report engine: catalogue, ad-hoc runs and saved reports."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Body, Query, Response
from sqlalchemy import select

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.exports import export_response, with_extension
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.models.identity import SavedReport
from app.services.audit_service import AuditService
from app.services.import_export_service import ImportExportService
from app.services.report_service import ReportResult, ReportService

router = APIRouter()


def _default_period(params: dict[str, Any]) -> dict[str, Any]:
    """Fill in a sensible default period when the caller omits the dates."""
    today = date.today()
    params.setdefault("date_to", today.isoformat())
    params.setdefault("date_from", (today - timedelta(days=30)).isoformat())
    return params


@router.get("/catalogue", summary="Every report the caller may run")
def catalogue(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.report.view")
    items = ReportService(db, current.company_id).available_reports()
    allowed = [
        item for item in items if current.is_superuser or current.can(item.get("permission") or "core.report.view")
    ]
    return {"items": allowed, "total": len(allowed)}


@router.post("/run/{code}", summary="Run a report with ad-hoc parameters")
def run_report(
    code: str,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    current.require("core.report.view")
    service = ReportService(db, current.company_id, user_id=current.id)
    params = _default_period(dict(payload or {}))
    result: ReportResult = service.run(code, params)
    return result.to_dict()


@router.get("/run/{code}", summary="Run a report with query-string parameters")
def run_report_get(
    code: str,
    db: DB,
    current: CurrentUserDep,
    date_from: str | None = None,
    date_to: str | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = Query(1000, ge=1, le=20000),
) -> dict[str, Any]:
    current.require("core.report.view")
    params: dict[str, Any] = {"limit": limit}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if branch_id:
        params["branch_id"] = str(branch_id)
    result: ReportResult = ReportService(db, current.company_id, user_id=current.id).run(
        code, _default_period(params)
    )
    return result.to_dict()


# --------------------------------------------------------------------------- #
# Saved reports
# --------------------------------------------------------------------------- #
@router.get("/saved", summary="Saved report configurations")
def list_saved(
    db: DB, current: CurrentUserDep, module: str | None = None, report_type: str | None = None
) -> dict[str, Any]:
    current.require("core.saved_report.view")
    stmt = select(SavedReport).where(
        SavedReport.company_id == current.company_id, SavedReport.deleted_at.is_(None)
    )
    if module:
        stmt = stmt.where(SavedReport.module == module)
    if report_type:
        stmt = stmt.where(SavedReport.report_type == report_type)
    rows = db.execute(stmt.order_by(SavedReport.code)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/saved", status_code=201, summary="Save a report configuration")
def save_report(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.saved_report.create")
    name = payload.get("name")
    code = payload.get("code") or payload.get("report_code")
    if not name or not code:
        raise ValidationFailure("name and code are required")
    existing = db.execute(
        select(SavedReport).where(SavedReport.company_id == current.company_id, SavedReport.code == code)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A saved report with this code already exists", code=code)
    row = SavedReport(
        company_id=current.company_id,
        code=str(code),
        name=name,
        name_ar=payload.get("name_ar"),
        module=payload.get("module") or str(code).split(".")[0],
        report_type=payload.get("report_type") or "custom",
        description=payload.get("description"),
        definition_json=payload.get("definition") or payload.get("parameters") or {},
        is_system=False,
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(row)
    db.flush()
    AuditService(db, audit_context(current)).log_create(row, entity_type="saved_report", label=row.name)
    return serialise(row)


@router.get("/saved/{report_id}", summary="Saved report definition")
def get_saved(report_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.saved_report.view")
    return serialise(_saved_or_404(db, current, report_id))


@router.patch("/saved/{report_id}", summary="Update a saved report")
def update_saved(report_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.saved_report.edit")
    row = _saved_or_404(db, current, report_id)
    previous = _snapshot(row)
    for source, field in (
        ("name", "name"),
        ("name_ar", "name_ar"),
        ("description", "description"),
        ("module", "module"),
        ("report_type", "report_type"),
        ("is_active", "is_active"),
    ):
        if source in payload and payload[source] is not None:
            setattr(row, field, payload[source])
    if payload.get("definition") is not None or payload.get("parameters") is not None:
        row.definition_json = payload.get("definition") or payload.get("parameters")
    db.flush()
    AuditService(db, audit_context(current)).log_update(
        row, previous, entity_type="saved_report", label=row.name
    )
    return serialise(row)


@router.delete("/saved/{report_id}", summary="Delete a saved report")
def delete_saved(report_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.saved_report.delete")
    row = _saved_or_404(db, current, report_id)
    if row.is_system and not current.is_superuser:
        raise ValidationFailure("System report definitions cannot be deleted")
    db.delete(row)
    db.flush()
    return {"id": str(report_id), "deleted": True}


@router.post("/saved/{report_id}/run", summary="Run a saved report with optional overrides")
def run_saved(
    report_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    current.require("core.saved_report.view")
    row = _saved_or_404(db, current, report_id)
    definition = dict(row.definition_json or {})
    params = dict(definition.get("parameters") or definition)
    params.update(payload or {})
    result: ReportResult = ReportService(db, current.company_id, user_id=current.id).run(
        definition.get("report_code", row.code), _default_period(params)
    )
    return result.to_dict()


def _saved_or_404(db: DB, current: CurrentUserDep, report_id: uuid.UUID) -> SavedReport:
    row = db.get(SavedReport, report_id)
    if row is None or row.company_id != current.company_id or row.deleted_at is not None:
        raise NotFoundError("Saved report not found", id=str(report_id))
    return row


def _snapshot(entity: Any) -> dict[str, Any]:
    from app.core.pagination import snapshot

    return snapshot(entity)


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
@router.post("/export/{code}", summary="Export a report as CSV or Excel")
def export_report(
    code: str,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
    file_format: str = Query("csv", pattern="^(csv|xlsx)$"),
) -> Response:
    current.require("core.report.export")
    params = _default_period(dict(payload or {}).get("parameters") or {})
    service = ImportExportService(db, current.company_id, user_id=current.id)
    data = service.export_report(code, params, file_format=file_format)
    return export_response(data, with_extension(code, file_format), file_format)


__all__ = ["router"]
