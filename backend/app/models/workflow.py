"""Reusable workflow / approval engine models.

A workflow definition targets a document type and holds ordered steps.  Each
step may carry conditions (amount thresholds, department, role...) evaluated by
:mod:`app.services.workflow_service`; the engine is document agnostic so new
approvable documents only need a definition row.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    WorkflowActionType,
    WorkflowInstanceStatus,
    WorkflowStepType,
    WorkflowTriggerType,
)
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class WorkflowDefinition(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "workflow_definitions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(
        String(32), default=WorkflowTriggerType.DOCUMENT_SUBMITTED.value, nullable=False
    )
    module: Mapped[str | None] = mapped_column(String(48))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applies_to_branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    applies_to_department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id")
    )
    conditions_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    allow_parallel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_approve_below: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    escalation_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="definition", cascade="all, delete-orphan", order_by="WorkflowStep.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_workflow_definitions_company_code"),
        Index("ix_workflow_definitions_document", "company_id", "document_type", "is_active"),
    )


class WorkflowStep(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "workflow_steps"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    step_type: Mapped[str] = mapped_column(String(24), default=WorkflowStepType.APPROVAL.value, nullable=False)
    #: role | user | manager | department_manager | creator_manager | specific_users
    approver_type: Mapped[str] = mapped_column(String(32), default="role", nullable=False)
    approver_role_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"))
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approver_user_ids: Mapped[list | None] = mapped_column(JSONType)
    approver_department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id")
    )
    conditions_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    max_amount: Mapped[Decimal | None] = mapped_column(Money)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_delegation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    skip_if_same_user: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timeout_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_timeout_action: Mapped[str] = mapped_column(String(24), default="escalate", nullable=False)
    notification_template: Mapped[str | None] = mapped_column(String(64))

    definition: Mapped[WorkflowDefinition] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("definition_id", "sequence_no", name="uq_workflow_steps_sequence"),
    )


class WorkflowInstance(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "workflow_instances"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_no: Mapped[str | None] = mapped_column(String(64))
    document_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(
        String(24), default=WorkflowInstanceStatus.PENDING.value, nullable=False, index=True
    )
    current_step_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("workflow_steps.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    comments: Mapped[str | None] = mapped_column(Text)
    context_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    actions: Mapped[list[WorkflowAction]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", order_by="WorkflowAction.created_at"
    )

    __table_args__ = (
        Index("ix_workflow_instances_document", "company_id", "document_type", "document_id"),
        Index("ix_workflow_instances_company_status", "company_id", "status"),
    )


class WorkflowAction(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Immutable audit of every approval decision."""

    __tablename__ = "workflow_actions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("workflow_steps.id"))
    step_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    action: Mapped[str] = mapped_column(String(24), default=WorkflowActionType.APPROVE.value, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    actor_name: Mapped[str | None] = mapped_column(String(200))
    comments: Mapped[str | None] = mapped_column(Text)
    delegated_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    instance: Mapped[WorkflowInstance] = relationship(back_populates="actions")

    __table_args__ = (Index("ix_workflow_actions_instance", "instance_id", "created_at"),)


class ApprovalDelegation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Delegate approval authority while a manager is away."""

    __tablename__ = "approval_delegations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delegator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delegate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document_types: Mapped[list | None] = mapped_column(JSONType)
    max_amount: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        Index("ix_approval_delegations_delegate", "company_id", "delegate_id", "is_active"),
    )


class WorkflowConditionTemplate(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Reusable condition snippets offered by the workflow designer."""

    __tablename__ = "workflow_condition_templates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    condition_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_workflow_condition_templates_code"),)
