"""Project management: projects, phases, tasks, milestones and timesheets."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

from app.core.enums import BillingMethod, DocumentStatus, Priority, ProjectStatus, TaskStatus
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    Quantity,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Project(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "projects"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_no: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    project_type: Mapped[str] = mapped_column(String(48), default="general", nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    division_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("divisions.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))

    status: Mapped[str] = mapped_column(String(24), default=ProjectStatus.DRAFT.value, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    billing_method: Mapped[str] = mapped_column(String(24), default=BillingMethod.FIXED_PRICE.value, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    actual_start_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    progress_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)

    contract_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    budget_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    budget_materials: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    budget_labor: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    budget_expenses: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    budget_subcontractors: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_materials: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_labor: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_expenses: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_subcontractors: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    invoiced_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    received_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    retention_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    retention_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    wip_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    revenue_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    cost_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    phases: Mapped[list[ProjectPhase]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectPhase.sequence_no"
    )
    tasks: Mapped[list[ProjectTask]] = relationship(back_populates="project", cascade="all, delete-orphan")
    milestones: Mapped[list[Milestone]] = relationship(cascade="all, delete-orphan", order_by="Milestone.due_date")
    billing_schedule: Mapped[list[ProjectBillingSchedule]] = relationship(
        cascade="all, delete-orphan", order_by="ProjectBillingSchedule.sequence_no"
    )
    resources: Mapped[list[ProjectResourcePlan]] = relationship(cascade="all, delete-orphan")

    @property
    def total_actual_cost(self) -> Decimal:
        return (
            Decimal(self.actual_materials or 0)
            + Decimal(self.actual_labor or 0)
            + Decimal(self.actual_expenses or 0)
            + Decimal(self.actual_subcontractors or 0)
        )

    @property
    def profit_amount(self) -> Decimal:
        return Decimal(self.invoiced_amount or 0) - self.total_actual_cost

    __table_args__ = (
        UniqueConstraint("company_id", "project_no", name="uq_projects_company_no"),
        Index("ix_projects_company_status", "company_id", "status"),
        Index("ix_projects_customer", "company_id", "customer_id"),
    )


class ProjectPhase(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "project_phases"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    progress_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=TaskStatus.TODO.value, nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    billing_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="phases")

    __table_args__ = (Index("ix_project_phases_project", "project_id", "sequence_no"),)


class ProjectTask(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "project_tasks"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_phases.id", ondelete="SET NULL")
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE")
    )
    task_no: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=TaskStatus.TODO.value, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    actual_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    progress_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dependency_ids: Mapped[list | None] = mapped_column(JSONType)
    tags: Mapped[list | None] = mapped_column(JSONType)
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_project_tasks_project_status", "company_id", "project_id", "status"),
        Index("ix_project_tasks_assignee", "company_id", "assignee_id", "due_date"),
    )


class Milestone(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "project_milestones"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("project_phases.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    billing_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class Timesheet(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "timesheets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    billable_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    billable_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(400))
    is_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    @property
    def document_date(self) -> date:
        """Uniform document interface: the start of the timesheet period."""
        return self.period_start

    lines: Mapped[list[TimesheetLine]] = relationship(
        back_populates="timesheet", cascade="all, delete-orphan", order_by="TimesheetLine.work_date"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_timesheets_company_no"),
        Index("ix_timesheets_employee_period", "company_id", "employee_id", "period_start"),
    )


class TimesheetLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "timesheet_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("project_tasks.id"))
    activity: Mapped[str | None] = mapped_column(String(250))
    hours: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cost_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    billable_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    notes: Mapped[str | None] = mapped_column(String(400))

    timesheet: Mapped[Timesheet] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("hours > 0", name="hours_positive"),)


class ProjectResourcePlan(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Planned materials / labour / equipment for a project phase."""

    __tablename__ = "project_resource_plans"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("project_phases.id"))
    resource_type: Mapped[str] = mapped_column(String(24), default="material", nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    description: Mapped[str | None] = mapped_column(String(250))
    planned_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    actual_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    planned_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    planned_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    actual_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_project_resource_plans_project", "company_id", "project_id", "resource_type"),)


class ProjectBillingSchedule(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Progress billing plan for a project (milestone or percentage based)."""

    __tablename__ = "project_billing_schedules"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str | None] = mapped_column(String(250))
    percentage: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    is_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    invoiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
