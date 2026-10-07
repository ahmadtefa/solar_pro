"""Workflow engine: definitions, steps, instances, approvals and delegations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailure
from app.models.identity import Role
from app.models.workflow import (
    ApprovalDelegation,
    WorkflowAction,
    WorkflowConditionTemplate,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
)
from app.services.audit_service import AuditService
from app.services.workflow_service import WorkflowService

router = APIRouter()


# --------------------------------------------------------------------------- #
# Definitions
# --------------------------------------------------------------------------- #
@router.get("/definitions", summary="Workflow definitions")
def list_definitions(
    db: DB,
    current: CurrentUserDep,
    document_type: str | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    current.require("workflow.workflow_definition.view")
    stmt = select(WorkflowDefinition).where(
        WorkflowDefinition.company_id == current.company_id, WorkflowDefinition.deleted_at.is_(None)
    )
    if document_type:
        stmt = stmt.where(WorkflowDefinition.document_type == document_type)
    if active_only:
        stmt = stmt.where(WorkflowDefinition.is_active.is_(True))
    rows = db.execute(stmt.order_by(WorkflowDefinition.document_type, WorkflowDefinition.priority)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/definitions/{definition_id}", summary="Definition with its approval steps")
def get_definition(definition_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.workflow_definition.view")
    definition = db.get(WorkflowDefinition, definition_id)
    if definition is None or definition.company_id != current.company_id:
        raise NotFoundError("Workflow definition not found", id=str(definition_id))
    steps = db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.company_id == current.company_id, WorkflowStep.definition_id == definition_id)
        .order_by(WorkflowStep.sequence_no)
    ).scalars().all()
    service = WorkflowService(db, current.company_id, user_id=current.id)
    return {
        **serialise(definition),
        "steps": [serialise(step) for step in steps],
        "approvers_preview": list(service.step_approvers_preview(definition)),
    }


@router.post("/definitions", status_code=201, summary="Create a workflow definition with its steps")
def create_definition(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.workflow_definition.create")
    document_type = payload.get("document_type")
    if not document_type:
        raise ValidationFailure("document_type is required")
    steps = payload.get("steps") or []
    definition = WorkflowDefinition(
        company_id=current.company_id,
        code=str(payload.get("code") or document_type.upper())[:64],
        name=payload.get("name") or f"{document_type} approval",
        name_ar=payload.get("name_ar"),
        description=payload.get("description"),
        document_type=document_type,
        trigger_type=payload.get("trigger_type") or "document_submitted",
        module=payload.get("module"),
        is_active=bool(payload.get("is_active", True)),
        is_default=bool(payload.get("is_default", False)),
        applies_to_branch_id=_uuid(payload.get("applies_to_branch_id")),
        applies_to_department_id=_uuid(payload.get("applies_to_department_id")),
        conditions_json=payload.get("conditions") or {},
        allow_parallel=bool(payload.get("allow_parallel", False)),
        auto_approve_below=_decimal(payload.get("auto_approve_below")),
        escalation_hours=payload.get("escalation_hours"),
        version=int(payload.get("version") or 1),
        priority=int(payload.get("priority") or 10),
    )
    db.add(definition)
    db.flush()
    created = 0
    for index, step in enumerate(steps, start=1):
        db.add(_step_from_payload(current, definition, step, sequence=index))
        created += 1
    if not steps:
        db.add(_step_from_payload(current, definition, {}, sequence=1))
        created = 1
    db.flush()
    AuditService(db, audit_context(current)).log_create(
        definition, entity_type="workflow_definition", label=definition.code
    )
    return {**serialise(definition), "steps": created}


@router.put("/definitions/{definition_id}/steps", summary="Replace the steps of a definition")
def set_steps(
    definition_id: uuid.UUID, payload: list[dict[str, Any]], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("workflow.workflow_definition.edit")
    definition = db.get(WorkflowDefinition, definition_id)
    if definition is None or definition.company_id != current.company_id:
        raise NotFoundError("Workflow definition not found", id=str(definition_id))
    existing = db.execute(
        select(WorkflowStep).where(WorkflowStep.definition_id == definition.id)
    ).scalars().all()
    for step in existing:
        db.delete(step)
    db.flush()
    for index, step in enumerate(payload, start=1):
        db.add(_step_from_payload(current, definition, step, sequence=index))
    db.flush()
    return {"definition_id": str(definition.id), "steps": len(payload)}


def _step_from_payload(
    current: CurrentUserDep, definition: WorkflowDefinition, payload: dict[str, Any], *, sequence: int
) -> WorkflowStep:
    role_id = _uuid(payload.get("approver_role_id"))
    approver_user_id = _uuid(payload.get("approver_user_id"))
    approver_type = payload.get("approver_type") or ("role" if role_id else "user")
    if approver_type == "role" and role_id is None:
        raise ValidationFailure("approver_role_id is required when approver_type is 'role'")
    if approver_type == "user" and approver_user_id is None:
        approver_user_id = current.id
    return WorkflowStep(
        company_id=current.company_id,
        definition_id=definition.id,
        sequence_no=int(payload.get("sequence_no") or sequence),
        name=payload.get("name") or f"Step {sequence}",
        name_ar=payload.get("name_ar"),
        step_type=payload.get("step_type") or "approval",
        approver_type=approver_type,
        approver_role_id=role_id,
        approver_user_id=approver_user_id,
        approver_user_ids=payload.get("approver_user_ids"),
        approver_department_id=_uuid(payload.get("approver_department_id")),
        conditions_json=payload.get("conditions") or {},
        min_amount=_decimal(payload.get("min_amount")),
        max_amount=_decimal(payload.get("max_amount")),
        is_required=bool(payload.get("is_required", True)),
        allow_delegation=bool(payload.get("allow_delegation", True)),
        skip_if_same_user=bool(payload.get("skip_if_same_user", False)),
        timeout_hours=payload.get("timeout_hours"),
        on_timeout_action=payload.get("on_timeout_action"),
        notify_on_enter=bool(payload.get("notify_on_enter", True)),
    )


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="condition-templates",
            model=WorkflowConditionTemplate,
            module="workflow",
            entity="workflow_definition",
            search_fields=["name", "code"],
            label_field="name",
            create_handler=guarded_create(WorkflowConditionTemplate),
        ),
        tags=["workflow"],
    ),
    prefix="/condition-templates",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="roles",
            model=Role,
            module="core",
            entity="role",
            search_fields=["code", "name"],
            label_field="name",
            soft_delete=False,
        ),
        tags=["workflow"],
    ),
    prefix="/approver-roles",
)

# --------------------------------------------------------------------------- #
# Instances and approvals
# --------------------------------------------------------------------------- #
@router.get("/instances", summary="Workflow instances")
def list_instances(
    db: DB,
    current: CurrentUserDep,
    document_type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    pending_for_me: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("workflow.workflow_instance.view")
    service = WorkflowService(db, current.company_id, user_id=current.id)
    if pending_for_me:
        rows = service.pending_for_user(current.id, limit=limit)
        return {"items": [serialise(row) for row in rows], "total": len(rows)}
    stmt = select(WorkflowInstance).where(WorkflowInstance.company_id == current.company_id)
    if document_type:
        stmt = stmt.where(WorkflowInstance.document_type == document_type)
    if status_filter:
        stmt = stmt.where(WorkflowInstance.status == status_filter)
    rows = db.execute(stmt.order_by(WorkflowInstance.started_at.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/instances/{instance_id}", summary="Instance with its approval history")
def get_instance(instance_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.workflow_instance.view")
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None or instance.company_id != current.company_id:
        raise NotFoundError("Workflow instance not found", id=str(instance_id))
    actions = db.execute(
        select(WorkflowAction)
        .where(WorkflowAction.instance_id == instance_id)
        .order_by(WorkflowAction.created_at)
    ).scalars().all()
    service = WorkflowService(db, current.company_id, user_id=current.id)
    return {
        **serialise(instance),
        "actions": [serialise(row) for row in actions],
        "pending_approvers": [str(item) for item in service.approvers_for(instance)],
    }


@router.post("/instances/{instance_id}/decide", summary="Approve, reject or delegate")
def decide(instance_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.approval.approve")
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None or instance.company_id != current.company_id:
        raise NotFoundError("Workflow instance not found", id=str(instance_id))
    action = (payload.get("action") or "").lower()
    if action not in {"approve", "reject", "cancel", "delegate"}:
        raise ValidationFailure("action must be approve, reject, cancel or delegate")
    if action == "reject" and not payload.get("comments"):
        raise ValidationFailure("A rejection comment is required")
    if action == "delegate" and not payload.get("delegate_to"):
        raise ValidationFailure("delegate_to is required to delegate an approval")
    service = WorkflowService(db, current.company_id, user_id=current.id)
    instance = service.decide(
        instance,
        action=action,
        user_id=current.id,
        actor_name=current.user.full_name,
        comments=payload.get("comments"),
        delegate_to=_uuid(payload.get("delegate_to")),
    )
    db.flush()
    return serialise(instance)


@router.get("/history/{document_type}/{document_id}", summary="Approval history of a document")
def document_history(document_type: str, document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.workflow_instance.view")
    service = WorkflowService(db, current.company_id, user_id=current.id)
    return {"items": service.history(document_type, document_id)}


@router.post("/instances/{instance_id}/cancel", summary="Cancel a running workflow")
def cancel_instance(
    instance_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    current.require("workflow.workflow_instance.cancel")
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None or instance.company_id != current.company_id:
        raise NotFoundError("Workflow instance not found", id=str(instance_id))
    if not payload.get("reason"):
        raise ValidationFailure("A reason is required to cancel a workflow")
    if instance.requested_by_id != current.id and not current.can("workflow.workflow_instance.cancel"):
        raise PermissionDeniedError("You cannot cancel this workflow")
    service = WorkflowService(db, current.company_id, user_id=current.id)
    service.cancel_for_document(instance.document_type, instance.document_id, reason=payload["reason"])
    db.flush()
    return serialise(instance)


# --------------------------------------------------------------------------- #
# Delegations
# --------------------------------------------------------------------------- #
@router.get("/delegations", summary="Approval delegations")
def list_delegations(db: DB, current: CurrentUserDep, mine: bool = False) -> dict[str, Any]:
    current.require("workflow.delegation.view")
    stmt = select(ApprovalDelegation).where(
        ApprovalDelegation.company_id == current.company_id, ApprovalDelegation.deleted_at.is_(None)
    )
    if mine:
        stmt = stmt.where(ApprovalDelegation.delegator_id == current.id)
    rows = db.execute(stmt.order_by(ApprovalDelegation.start_date.desc())).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/delegations", status_code=201, summary="Delegate approvals while away")
def create_delegation(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.delegation.create")
    to_user_id = _uuid(payload.get("to_user_id") or payload.get("delegate_to_id"))
    if to_user_id is None:
        raise ValidationFailure("to_user_id is required")
    from datetime import date as date_type

    delegation = ApprovalDelegation(
        company_id=current.company_id,
        delegator_id=current.id,
        delegate_id=to_user_id,
        start_date=date_type.fromisoformat(payload["start_date"]) if payload.get("start_date") else date_type.today(),
        end_date=date_type.fromisoformat(payload["end_date"]) if payload.get("end_date") else None,
        document_types=payload.get("document_types"),
        max_amount=_decimal(payload.get("max_amount")),
        reason=payload.get("reason"),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(delegation)
    db.flush()
    AuditService(db, audit_context(current)).log_create(
        delegation, entity_type="approval_delegation", label=str(current.user.full_name)
    )
    return serialise(delegation)


@router.delete("/delegations/{delegation_id}", summary="Revoke a delegation")
def revoke_delegation(delegation_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.delegation.delete")
    delegation = db.get(ApprovalDelegation, delegation_id)
    if delegation is None or delegation.company_id != current.company_id:
        raise NotFoundError("Delegation not found", id=str(delegation_id))
    if delegation.delegator_id != current.id and not current.is_superuser:
        raise PermissionDeniedError("Only the delegating user can revoke this delegation")
    db.delete(delegation)
    db.flush()
    return {"id": str(delegation_id), "revoked": True}


# --------------------------------------------------------------------------- #
# Dashboards for approvers
# --------------------------------------------------------------------------- #
@router.get("/my-approvals", summary="My pending approvals with amounts")
def my_approvals(db: DB, current: CurrentUserDep, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    current.require("workflow.approval.view")
    service = WorkflowService(db, current.company_id, user_id=current.id)
    rows = service.pending_for_user(current.id, limit=limit)
    now = datetime.now(UTC)
    items = []
    for row in rows:
        payload = serialise(row)
        started = getattr(row, "started_at", None)
        payload["waiting_days"] = (now - _aware(started)).days if started else 0
        payload["due_at"] = row.due_at.isoformat() if row.due_at else None
        items.append(payload)
    return {"items": items, "total": len(items)}


@router.get("/statistics", summary="Approval workload statistics")
def statistics(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("workflow.workflow_instance.view")
    rows = db.execute(
        select(WorkflowInstance.status, func.count(WorkflowInstance.id))
        .where(WorkflowInstance.company_id == current.company_id)
        .group_by(WorkflowInstance.status)
    ).all()
    by_type = db.execute(
        select(WorkflowInstance.document_type, func.count(WorkflowInstance.id))
        .where(WorkflowInstance.company_id == current.company_id)
        .group_by(WorkflowInstance.document_type)
    ).all()
    return {
        "by_status": [{"status": row[0], "count": int(row[1])} for row in rows],
        "by_document_type": [{"document_type": row[0], "count": int(row[1])} for row in by_type],
    }


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


__all__ = ["router"]
