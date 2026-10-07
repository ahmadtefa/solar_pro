"""Reusable workflow / approval engine.

Highlights
----------
* Definitions are data: document type, trigger, ordered steps with conditions
  (amount thresholds, departments, roles) - no code change to add approvals.
* ``start`` evaluates the definition conditions, auto-approves below the
  configured threshold, and otherwise waits for the first required approver.
* ``decide`` records immutable :class:`WorkflowAction` rows and drives the
  instance to the next step, mapping the outcome back onto the document.
* ``approvers_for`` resolves who must act (role, specific users, department
  manager, requester's manager) and applies delegations.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    NotificationType,
    WorkflowActionType,
    WorkflowInstanceStatus,
    WorkflowStepType,
    WorkflowTriggerType,
)
from app.core.errors import BusinessRuleError, PermissionDeniedError
from app.models.hr import Employee
from app.models.identity import Role, User, UserRole
from app.models.workflow import (
    ApprovalDelegation,
    WorkflowAction,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
)
from app.services.audit_service import AuditContext, AuditService
from app.services.notification_service import NotificationService

#: Fee free statuses that terminate an instance.
TERMINAL = {
    WorkflowInstanceStatus.APPROVED.value,
    WorkflowInstanceStatus.REJECTED.value,
    WorkflowInstanceStatus.CANCELLED.value,
}


class WorkflowService:
    def __init__(
        self,
        db: Session,
        company_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        audit_context: AuditContext | None = None,
    ) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, audit_context or AuditContext(company_id=company_id, user_id=user_id))
        self.notifications = NotificationService(db, company_id)

    # ------------------------------------------------------------ definitions
    def find_definition(
        self,
        document_type: str,
        *,
        trigger: str = WorkflowTriggerType.DOCUMENT_SUBMITTED.value,
        amount: Decimal | None = None,
        branch_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> WorkflowDefinition | None:
        stmt = (
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.company_id == self.company_id,
                WorkflowDefinition.document_type == document_type,
                WorkflowDefinition.is_active.is_(True),
                WorkflowDefinition.trigger_type == trigger,
                WorkflowDefinition.deleted_at.is_(None),
            )
            .order_by(WorkflowDefinition.priority.asc(), WorkflowDefinition.created_at.desc())
        )
        candidates = list(self.db.execute(stmt).scalars().all())
        for definition in candidates:
            if definition.applies_to_branch_id and branch_id and definition.applies_to_branch_id != branch_id:
                continue
            if definition.applies_to_department_id and department_id and definition.applies_to_department_id != department_id:
                continue
            if not self._conditions_match(definition.conditions_json, amount, context):
                continue
            return definition
        return candidates[0] if candidates else None

    @staticmethod
    def _conditions_match(conditions: dict[str, Any] | None, amount: Decimal | None, context: dict[str, Any] | None) -> bool:
        if not conditions:
            return True
        if amount is not None:
            if "min_amount" in conditions and amount < Decimal(str(conditions["min_amount"])):
                return False
            if "max_amount" in conditions and amount > Decimal(str(conditions["max_amount"])):
                return False
        payload = context or {}
        for key in ("branch_id", "department_id", "division_id", "customer_id", "supplier_id", "project_id"):
            expected = conditions.get(key)
            if expected and str(payload.get(key)) != str(expected):
                return False
        for flag in ("priority", "category", "expense_type", "work_order_type"):
            if conditions.get(flag) and str(payload.get(flag)) != str(conditions[flag]):
                return False
        return True

    # ---------------------------------------------------------------- instance
    def start(
        self,
        *,
        document_type: str,
        document: Any,
        amount: Decimal | None = None,
        context: dict[str, Any] | None = None,
        requester_id: uuid.UUID | None = None,
        auto_approve_below: Decimal | None = None,
    ) -> WorkflowInstance | None:
        """Create an approval instance for a document, or ``None`` if no workflow."""
        requester_id = requester_id or self.user_id
        document_no = getattr(document, "document_no", None) or getattr(document, "request_no", None)
        document_amount = Decimal(amount if amount is not None else getattr(document, "total_amount", 0) or 0)
        definition = self.find_definition(
            document_type,
            amount=document_amount,
            branch_id=getattr(document, "branch_id", None),
            department_id=getattr(document, "department_id", None),
            context=context,
        )
        if definition is None:
            return None

        threshold = auto_approve_below if auto_approve_below is not None else definition.auto_approve_below
        instance = WorkflowInstance(
            company_id=self.company_id,
            definition_id=definition.id,
            document_type=document_type,
            document_id=document.id,
            document_no=document_no,
            document_amount=document_amount,
            branch_id=getattr(document, "branch_id", None),
            department_id=getattr(document, "department_id", None),
            requested_by_id=requester_id,
            status=WorkflowInstanceStatus.IN_PROGRESS.value,
            current_step_no=1,
            started_at=datetime.now(UTC),
            context_json=context or {},
        )
        self.db.add(instance)
        self.db.flush()

        if threshold and document_amount < Decimal(str(threshold)):
            self._apply_step(instance, None)
            self._complete(instance, WorkflowInstanceStatus.APPROVED.value, remarks="Auto approved below threshold")
            return instance

        first_step = self._step_for(definition, instance.current_step_no)
        if first_step is None:
            self._complete(instance, WorkflowInstanceStatus.APPROVED.value, remarks="No approval steps configured")
            return instance
        instance.current_step_id = first_step.id
        self.db.flush()
        self._notify_approvers(instance, first_step)
        return instance

    def _step_for(self, definition: WorkflowDefinition, sequence_no: int) -> WorkflowStep | None:
        steps = sorted(definition.steps, key=lambda step: step.sequence_no)
        for step in steps:
            if step.sequence_no >= sequence_no:
                return step
        return None

    def _next_step(self, instance: WorkflowInstance, current: WorkflowStep | None) -> WorkflowStep | None:
        definition = self.db.get(WorkflowDefinition, instance.definition_id)
        if definition is None:
            return None
        steps = sorted(definition.steps, key=lambda step: step.sequence_no)
        if current is None:
            return steps[0] if steps else None
        for step in steps:
            if step.sequence_no > current.sequence_no:
                if step.conditions_json:
                    if not self._conditions_match(step.conditions_json, instance.document_amount, instance.context_json):
                        continue
                if step.min_amount and instance.document_amount < Decimal(step.min_amount):
                    continue
                if step.max_amount is not None and instance.document_amount > Decimal(step.max_amount):
                    continue
                return step
        return None

    def _apply_step(self, instance: WorkflowInstance, step: WorkflowStep | None) -> None:
        """Execute non approval step types (notification / auto approve)."""
        if step is None:
            return
        if step.step_type == WorkflowStepType.NOTIFICATION.value:
            self.notifications.notify_users(
                self._user_ids_for_step(step, instance),
                title=f"{instance.document_type.replace('_', ' ').title()} {instance.document_no or ''}".strip(),
                body=step.name,
                notification_type=NotificationType.INFO.value,
                entity_type=instance.document_type,
                entity_id=instance.document_id,
            )

    # -------------------------------------------------------------- approvers
    def _user_ids_for_step(self, step: WorkflowStep, instance: WorkflowInstance) -> list[uuid.UUID]:
        users: list[uuid.UUID] = []
        if step.approver_type == "user" and step.approver_user_id:
            users.append(step.approver_user_id)
        elif step.approver_type == "specific_users" and step.approver_user_ids:
            users.extend(uuid.UUID(str(value)) for value in step.approver_user_ids)
        elif step.approver_type == "role" and step.approver_role_id:
            rows = self.db.execute(
                select(UserRole.user_id).where(
                    UserRole.company_id == self.company_id, UserRole.role_id == step.approver_role_id
                )
            ).scalars().all()
            users.extend(rows)
        elif step.approver_type in {"manager", "creator_manager"}:
            users.extend(self._manager_of(instance.requested_by_id))
        elif step.approver_type == "department_manager" and instance.department_id:
            manager = self.db.execute(
                select(Employee.user_id).where(
                    Employee.company_id == self.company_id, Employee.department_id == instance.department_id
                ).limit(1)
            ).scalars().first()
            if manager:
                users.append(manager)
        return self.apply_delegations(list(dict.fromkeys(users)))

    def _manager_of(self, user_id: uuid.UUID | None) -> list[uuid.UUID]:
        if not user_id:
            return []
        employee = self.db.execute(
            select(Employee).where(Employee.company_id == self.company_id, Employee.user_id == user_id)
        ).scalars().first()
        if employee is None or employee.manager_id is None:
            return []
        manager = self.db.get(Employee, employee.manager_id)
        return [manager.user_id] if manager and manager.user_id else []

    def apply_delegations(self, user_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        """Replace absent approvers with their active delegates."""
        if not user_ids:
            return []
        now = datetime.now(UTC)
        delegations = self.db.execute(
            select(ApprovalDelegation).where(
                ApprovalDelegation.company_id == self.company_id,
                ApprovalDelegation.is_active.is_(True),
                ApprovalDelegation.delegator_id.in_(list(user_ids)),
                ApprovalDelegation.start_date <= now,
                ApprovalDelegation.end_date >= now,
            )
        ).scalars().all()
        mapping = {delegation.delegator_id: delegation.delegate_id for delegation in delegations}
        resolved = [mapping.get(user_id, user_id) for user_id in user_ids]
        return list(dict.fromkeys(resolved))

    def approvers_for(self, instance: WorkflowInstance) -> list[uuid.UUID]:
        if instance.status in TERMINAL:
            return []
        step = self.db.get(WorkflowStep, instance.current_step_id) if instance.current_step_id else None
        if step is None:
            return []
        return self._user_ids_for_step(step, instance)

    def pending_for_user(self, user_id: uuid.UUID, *, limit: int = 100) -> list[WorkflowInstance]:
        instances = self.db.execute(
            select(WorkflowInstance)
            .where(
                WorkflowInstance.company_id == self.company_id,
                WorkflowInstance.status == WorkflowInstanceStatus.IN_PROGRESS.value,
            )
            .order_by(WorkflowInstance.created_at.desc())
            .limit(limit * 3)
        ).scalars().all()
        return [instance for instance in instances if user_id in self.approvers_for(instance)][:limit]

    def history(self, document_type: str, document_id: uuid.UUID) -> list[dict[str, Any]]:
        instances = self.db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.company_id == self.company_id,
                WorkflowInstance.document_type == document_type,
                WorkflowInstance.document_id == document_id,
            )
        ).scalars().all()
        history: list[dict[str, Any]] = []
        for instance in instances:
            definition = self.db.get(WorkflowDefinition, instance.definition_id)
            for action in sorted(instance.actions, key=lambda row: row.created_at):
                history.append(
                    {
                        "instance_id": instance.id,
                        "definition": definition.name if definition else None,
                        "step_no": action.step_no,
                        "action": action.action,
                        "actor_id": action.actor_id,
                        "actor_name": action.actor_name,
                        "comments": action.comments,
                        "at": action.created_at,
                    }
                )
        return history

    # ---------------------------------------------------------------- decide
    def decide(
        self,
        instance: WorkflowInstance,
        *,
        action: str,
        user_id: uuid.UUID,
        actor_name: str | None = None,
        comments: str | None = None,
        ip_address: str | None = None,
        delegate_to: uuid.UUID | None = None,
    ) -> WorkflowInstance:
        if instance.status in TERMINAL:
            raise BusinessRuleError("This approval request is already closed")
        if action in {WorkflowActionType.APPROVE.value, WorkflowActionType.REJECT.value, WorkflowActionType.RETURN.value}:
            allowed = self.approvers_for(instance)
            if user_id not in allowed and not self._is_admin(user_id):
                raise PermissionDeniedError("You are not an approver for this step")

        step = self.db.get(WorkflowStep, instance.current_step_id) if instance.current_step_id else None
        self.db.add(
            WorkflowAction(
                company_id=self.company_id,
                instance_id=instance.id,
                step_id=instance.current_step_id,
                step_no=instance.current_step_no,
                action=action,
                actor_id=user_id,
                actor_name=actor_name,
                comments=comments,
                delegated_to_id=delegate_to if action == WorkflowActionType.DELEGATE.value else None,
                ip_address=ip_address,
                decided_at=datetime.now(UTC),
            )
        )
        instance.comments = comments or instance.comments
        self.db.flush()

        if action == WorkflowActionType.REJECT.value:
            self._complete(instance, WorkflowInstanceStatus.REJECTED.value, user_id=user_id, remarks=comments)
        elif action == WorkflowActionType.CANCEL.value:
            self._complete(instance, WorkflowInstanceStatus.CANCELLED.value, user_id=user_id, remarks=comments)
        elif action == WorkflowActionType.DELEGATE.value and delegate_to:
            # Move the current step to the delegate (recorded, no step advance).
            self.notifications.notify_users(
                [delegate_to],
                title="Approval delegated to you",
                body=f"{instance.document_type} {instance.document_no or ''}".strip(),
                notification_type=NotificationType.APPROVAL.value,
                entity_type=instance.document_type,
                entity_id=instance.document_id,
            )
        elif action == WorkflowActionType.RETURN.value:
            instance.current_step_no = 1
            first = self._step_for(self.db.get(WorkflowDefinition, instance.definition_id), 1)
            instance.current_step_id = first.id if first else None
            self._notify_approvers(instance, first)
        else:  # approve
            next_step = self._next_step(instance, step)
            if next_step is None:
                self._complete(instance, WorkflowInstanceStatus.APPROVED.value, user_id=user_id, remarks=comments)
            else:
                instance.current_step_no = next_step.sequence_no
                instance.current_step_id = next_step.id
                self.db.flush()
                self._notify_approvers(instance, next_step)
        self.db.flush()
        return instance

    def _is_admin(self, user_id: uuid.UUID) -> bool:
        user = self.db.get(User, user_id)
        if user and user.is_superuser:
            return True
        admin_roles = self.db.execute(
            select(Role.id).where(Role.company_id == self.company_id, Role.code.in_(["company_admin", "general_manager"]))
        ).scalars().all()
        if not admin_roles:
            return False
        membership = self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(list(admin_roles)))
        ).scalars().first()
        return membership is not None

    def _complete(
        self,
        instance: WorkflowInstance,
        status: str,
        *,
        user_id: uuid.UUID | None = None,
        remarks: str | None = None,
    ) -> None:
        instance.status = status
        instance.completed_at = datetime.now(UTC)
        instance.completed_by_id = user_id
        self.db.flush()
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="workflow_instance",
            entity_id=instance.id,
            entity_label=str(instance.document_no),
            new_values={"status": status},
            remarks=remarks,
        )
        if instance.requested_by_id:
            self.notifications.notify_users(
                [instance.requested_by_id],
                title=f"Approval {status}: {instance.document_type.replace('_', ' ').title()}",
                body=f"{instance.document_no or ''} was {status}",
                notification_type=NotificationType.APPROVAL.value,
                entity_type=instance.document_type,
                entity_id=instance.document_id,
            )

    def _notify_approvers(self, instance: WorkflowInstance, step: WorkflowStep | None) -> None:
        if step is None:
            return
        user_ids = self._user_ids_for_step(step, instance)
        if not user_ids:
            return
        self.notifications.notify_users(
            user_ids,
            title=f"Approval required: {instance.document_type.replace('_', ' ').title()}",
            body=f"{step.name} — {instance.document_no or ''} ({instance.document_amount})",
            notification_type=NotificationType.APPROVAL.value,
            entity_type=instance.document_type,
            entity_id=instance.document_id,
        )

    # -------------------------------------------------------------- utilities
    def status_of(self, document_type: str, document_id: uuid.UUID) -> WorkflowInstance | None:
        return self.db.execute(
            select(WorkflowInstance)
            .where(
                WorkflowInstance.company_id == self.company_id,
                WorkflowInstance.document_type == document_type,
                WorkflowInstance.document_id == document_id,
            )
            .order_by(WorkflowInstance.created_at.desc())
        ).scalars().first()

    def cancel_for_document(self, document_type: str, document_id: uuid.UUID, *, reason: str) -> None:
        instance = self.status_of(document_type, document_id)
        if instance and instance.status not in TERMINAL:
            self._complete(instance, WorkflowInstanceStatus.CANCELLED.value, remarks=reason)

    def step_approvers_preview(self, definition: WorkflowDefinition, amount: Decimal | None = None) -> Iterable[dict[str, Any]]:
        for step in sorted(definition.steps, key=lambda row: row.sequence_no):
            users = []
            if step.approver_role_id:
                users = list(
                    self.db.execute(
                        select(User.full_name)
                        .join(UserRole, UserRole.user_id == User.id)
                        .where(UserRole.role_id == step.approver_role_id)
                    ).scalars().all()
                )
            yield {
                "sequence_no": step.sequence_no,
                "name": step.name,
                "type": step.step_type,
                "approver_type": step.approver_type,
                "approvers": users,
                "min_amount": str(step.min_amount or 0),
                "max_amount": str(step.max_amount) if step.max_amount is not None else None,
            }
