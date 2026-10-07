"""Projects: delivery, phases, tasks, milestones, timesheets, billing and profitability."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError, ValidationFailure
from app.models.projects import (
    Milestone,
    Project,
    ProjectBillingSchedule,
    ProjectPhase,
    ProjectResourcePlan,
    ProjectTask,
    Timesheet,
)
from app.services.audit_service import AuditService
from app.services.projects_service import (
    MilestoneService,
    ProjectBillingService,
    ProjectService,
    TimesheetService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
@router.get("/projects", summary="Projects with budget and margin")
def list_projects(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    customer_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("projects.project.view")
    stmt = select(Project).where(Project.company_id == current.company_id, Project.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Project.name.ilike(f"%{q}%") | Project.project_no.ilike(f"%{q}%") | Project.customer_name.ilike(f"%{q}%")
        )
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if customer_id:
        stmt = stmt.where(Project.customer_id == customer_id)
    if manager_id:
        stmt = stmt.where(Project.project_manager_id == manager_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/projects", status_code=201, summary="Create a project")
def create_project(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.create")
    project = ProjectService(db, current.company_id, user_id=current.id).create(payload)
    AuditService(db, audit_context(current)).log_create(project, entity_type="project", label=project.project_no)
    return serialise(project)


@router.get("/projects/{project_id}", summary="Project 360: phases, tasks, milestones and profitability")
def get_project(project_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.view")
    service = ProjectService(db, current.company_id, user_id=current.id)
    project = service.get(project_id)
    return {
        **serialise(project),
        "phases": [serialise(row) for row in project.phases],
        "tasks": [serialise(row) for row in project.tasks],
        "milestones": [serialise(row) for row in project.milestones],
        "billing_schedule": [serialise(row) for row in project.billing_schedule],
        "resource_plan": [serialise(row) for row in project.resources],
        "profitability": service.profitability(project_id),
        "billable": service.billable_summary(project_id),
    }


@router.patch("/projects/{project_id}", summary="Update a project")
def update_project(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.edit")
    project = ProjectService(db, current.company_id, user_id=current.id).update(project_id, payload)
    return serialise(project)


@router.post("/projects/{project_id}/status", summary="Change the project status")
def change_status(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.edit")
    project = ProjectService(db, current.company_id, user_id=current.id).change_status(
        project_id, payload.get("status"), reason=payload.get("reason")
    )
    return serialise(project)


@router.get("/projects/{project_id}/profitability", summary="Project profitability")
def project_profitability(project_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.profitability.view")
    return ProjectService(db, current.company_id, user_id=current.id).profitability(project_id)


@router.get("/projects/{project_id}/billable", summary="What is still billable on the project")
def project_billable(project_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project_billing.view")
    return ProjectService(db, current.company_id, user_id=current.id).billable_summary(project_id)


@router.post("/projects/{project_id}/progress", summary="Recalculate progress from tasks and milestones")
def recalculate_progress(project_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.edit")
    project = ProjectService(db, current.company_id, user_id=current.id).recalculate_progress(project_id)
    return {"project_id": str(project.id), "progress_percent": str(project.progress_percent)}


@router.post("/projects/{project_id}/costs", summary="Record a cost line against the project")
def record_cost(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project.edit")
    result = ProjectService(db, current.company_id, user_id=current.id).record_cost(
        project_id,
        material=payload.get("material", 0),
        labour=payload.get("labour", 0),
        expense=payload.get("expense", 0),
        subcontractor=payload.get("subcontractor", 0),
        resource_id=payload.get("resource_id"),
        phase_id=payload.get("phase_id"),
    )
    return result if isinstance(result, dict) else serialise(result)


# --------------------------------------------------------------------------- #
# Phases, tasks, milestones, resources
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="phases",
            model=ProjectPhase,
            module="projects",
            entity="project_phase",
            search_fields=["code", "name"],
            label_field="name",
            filters={"project_id": "project_id", "status": "status"},
            create_handler=guarded_create(ProjectPhase),
        ),
        tags=["projects"],
    ),
    prefix="/project-phases",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="tasks",
            model=ProjectTask,
            module="projects",
            entity="task",
            search_fields=["code", "name"],
            label_field="name",
            filters={"project_id": "project_id", "status": "status", "phase_id": "phase_id"},
            create_handler=guarded_create(ProjectTask),
        ),
        tags=["projects"],
    ),
    prefix="/project-tasks",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="resource-plan",
            model=ProjectResourcePlan,
            module="projects",
            entity="project_resource",
            filters={"project_id": "project_id", "employee_id": "employee_id"},
            create_handler=guarded_create(ProjectResourcePlan),
        ),
        tags=["projects"],
    ),
    prefix="/project-resources",
)


@router.post("/projects/{project_id}/phases", status_code=201, summary="Add a phase")
def add_phase(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project_phase.create")
    phase = ProjectService(db, current.company_id, user_id=current.id).add_phase(project_id, payload)
    return serialise(phase)


@router.patch("/project-phases/{phase_id}", summary="Update a phase")
def update_phase(phase_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project_phase.edit")
    phase = ProjectService(db, current.company_id, user_id=current.id).update_phase(phase_id, payload)
    return serialise(phase)


@router.post("/projects/{project_id}/tasks", status_code=201, summary="Add a task")
def add_task(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.task.create")
    task = ProjectService(db, current.company_id, user_id=current.id).add_task(project_id, payload)
    return serialise(task)


@router.patch("/project-tasks/{task_id}", summary="Update a task")
def update_task(task_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.task.edit")
    task = ProjectService(db, current.company_id, user_id=current.id).update_task(task_id, payload)
    return serialise(task)


@router.post("/project-tasks/{task_id}/complete", summary="Complete a task")
def complete_task(
    task_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("projects.task.edit")
    task = ProjectService(db, current.company_id, user_id=current.id).complete_task(
        task_id, actual_hours=payload.get("actual_hours")
    )
    return serialise(task)


# --------------------------------------------------------------------------- #
# Milestones and billing
# --------------------------------------------------------------------------- #
milestone_router = APIRouter(tags=["projects"])


@milestone_router.get("/milestones", summary="Milestones across projects")
def list_milestones(
    db: DB,
    current: CurrentUserDep,
    project_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    due_before: date | None = None,
) -> dict[str, Any]:
    current.require("projects.milestone.view")
    stmt = select(Milestone).where(Milestone.company_id == current.company_id, Milestone.deleted_at.is_(None))
    if project_id:
        stmt = stmt.where(Milestone.project_id == project_id)
    if status_filter:
        stmt = stmt.where(Milestone.status == status_filter)
    if due_before:
        stmt = stmt.where(Milestone.due_date <= due_before)
    rows = db.execute(stmt.order_by(Milestone.due_date.asc().nulls_last())).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@milestone_router.post("/projects/{project_id}/milestones", status_code=201, summary="Add a milestone")
def add_milestone(
    project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("projects.milestone.create")
    milestone = MilestoneService(db, current.company_id, user_id=current.id).create(project_id, payload)
    return serialise(milestone)


@milestone_router.post("/milestones/{document_id}/complete", summary="Complete a milestone")
def complete_milestone(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.milestone.edit")
    service = MilestoneService(db, current.company_id, user_id=current.id)
    milestone = db.get(Milestone, document_id)
    if milestone is None or milestone.company_id != current.company_id:
        raise NotFoundError("Milestone not found", id=str(document_id))
    milestone = service.complete(milestone.id)
    return serialise(milestone)


@milestone_router.post("/milestones/{document_id}/bill", summary="Invoice a milestone")
def bill_milestone(
    document_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    current.require("projects.project_billing.create")
    service = ProjectBillingService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    invoice = service.bill_milestone(
        document_id,
        product_id=payload.get("product_id"),
        tax_id=payload.get("tax_id"),
        quantity_value=Decimal(str(payload.get("quantity", 1))),
        post=bool(payload.get("post", False)),
        allow_credit_override=bool(payload.get("allow_credit_override", False)),
    )
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


router.include_router(milestone_router)


@router.post("/projects/{project_id}/invoices", status_code=201, summary="Create a project invoice")
def create_project_invoice(
    project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("projects.project_billing.create")
    service = ProjectBillingService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    invoice = service.create_invoice(project_id, payload)
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


@router.post("/projects/{project_id}/bill-progress", summary="Invoice a progress percentage")
def bill_progress(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project_billing.create")
    if payload.get("percentage") is None or not payload.get("product_id"):
        raise ValidationFailure("percentage and product_id are required")
    service = ProjectBillingService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    invoice = service.bill_progress(
        project_id,
        percentage=payload["percentage"],
        product_id=payload["product_id"],
        apply_retention=bool(payload.get("apply_retention", False)),
        tax_id=payload.get("tax_id"),
        post=bool(payload.get("post", False)),
        allow_credit_override=bool(payload.get("allow_credit_override", False)),
    )
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


@router.post("/projects/{project_id}/bill-timesheets", summary="Invoice approved timesheets")
def bill_timesheets(project_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.project_billing.create")
    if not payload.get("product_id"):
        raise ValidationFailure("product_id is required")
    service = ProjectBillingService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    invoice = service.bill_timesheets(
        project_id,
        product_id=payload["product_id"],
        date_from=date.fromisoformat(payload["date_from"]) if payload.get("date_from") else None,
        date_to=date.fromisoformat(payload["date_to"]) if payload.get("date_to") else None,
        tax_id=payload.get("tax_id"),
        post=bool(payload.get("post", False)),
        allow_credit_override=bool(payload.get("allow_credit_override", False)),
    )
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="billing-schedule",
            model=ProjectBillingSchedule,
            module="projects",
            entity="project_billing",
            filters={"project_id": "project_id", "status": "status"},
            create_handler=guarded_create(ProjectBillingSchedule),
        ),
        tags=["projects"],
    ),
    prefix="/billing-schedule",
)


# --------------------------------------------------------------------------- #
# Timesheets
# --------------------------------------------------------------------------- #
router.include_router(
    build_document_router(
        DocumentSpec(
            name="timesheets",
            service=TimesheetService,
            label="timesheets",
            tag="projects",
            party_field="employee_id",
            search_fields=("document_no", "reference"),
        )
    ),
    prefix="/timesheets",
)


@router.put("/timesheets/{document_id}/lines", summary="Replace the lines of a draft timesheet")
def update_timesheet_lines(
    document_id: uuid.UUID, payload: list[dict[str, Any]], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("projects.timesheet.edit")
    service = TimesheetService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    timesheet = service.update_lines(document_id, payload)
    db.flush()
    return {**serialise(timesheet), "lines": [serialise(line) for line in timesheet.lines]}


@router.get("/timesheets/summary", summary="Hours per employee and project for a period")
def timesheet_summary(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("projects.timesheet.view")
    from app.models.projects import TimesheetLine

    today = date.today()
    start = date_from or today.replace(day=1)
    end = date_to or today
    stmt = (
        select(
            Timesheet.employee_id,
            Timesheet.project_id,
            func.coalesce(func.sum(TimesheetLine.hours), 0),
            func.coalesce(func.sum(TimesheetLine.billable_hours), 0),
            func.coalesce(func.sum(TimesheetLine.billable_amount), 0),
        )
        .join(TimesheetLine, TimesheetLine.timesheet_id == Timesheet.id)
        .where(
            Timesheet.company_id == current.company_id,
            Timesheet.document_date >= start,
            Timesheet.document_date <= end,
            Timesheet.status.in_(["posted", "approved", "fulfilled"]),
        )
        .group_by(Timesheet.employee_id, Timesheet.project_id)
    )
    if project_id:
        stmt = stmt.where(Timesheet.project_id == project_id)
    rows = db.execute(stmt).all()
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "items": [
            {
                "employee_id": str(row[0]) if row[0] else None,
                "project_id": str(row[1]) if row[1] else None,
                "hours": str(row[2]),
                "billable_hours": str(row[3]),
                "billable_amount": str(row[4]),
            }
            for row in rows
        ],
    }


@router.get("/reports/project-profitability", summary="Profitability of every project")
def all_project_profitability(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("projects.profitability.view")
    service = ProjectService(db, current.company_id, user_id=current.id)
    projects = db.execute(
        select(Project).where(Project.company_id == current.company_id, Project.deleted_at.is_(None))
    ).scalars().all()
    return {"items": [service.profitability(project.id) for project in projects]}


__all__ = ["router"]
