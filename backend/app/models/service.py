"""Service management: requests, tickets, work orders, contracts and warranty."""

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

from app.core.enums import (
    DocumentStatus,
    Priority,
    ServiceContractStatus,
    TicketStatus,
    WorkOrderType,
)
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
from app.models.mixins import DocumentHeaderMixin


class ServiceRequest(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Incoming customer request (may become one or more work orders)."""

    __tablename__ = "service_requests"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("contacts.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("service_contracts.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    site_address: Mapped[str | None] = mapped_column(String(400))
    request_type: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=TicketStatus.NEW.value, nullable=False, index=True)
    reported_by: Mapped[str | None] = mapped_column(String(200))
    reported_phone: Mapped[str | None] = mapped_column(String(40))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferred_visit_date: Mapped[date | None] = mapped_column(Date)
    is_under_warranty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "request_no", name="uq_service_requests_company_no"),
        Index("ix_service_requests_customer", "company_id", "customer_id", "status"),
    )


class Ticket(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Support ticket with conversation thread and SLA tracking."""

    __tablename__ = "tickets"

    @property
    def document_date(self) -> object:
        """Uniform document interface: when the ticket was raised."""
        return self.created_at.date() if self.created_at else date.today()

    @property
    def document_no(self) -> str:
        """Uniform document interface: this record's natural number."""
        return self.ticket_no

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_requests.id", ondelete="SET NULL")
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(48))
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=TicketStatus.NEW.value, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(24), default="phone", nullable=False)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    assigned_team: Mapped[str | None] = mapped_column(String(64))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_response_minutes: Mapped[int | None] = mapped_column(Integer)
    sla_resolution_minutes: Mapped[int | None] = mapped_column(Integer)
    is_sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    satisfaction_score: Mapped[int | None] = mapped_column(Integer)
    resolution: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.created_at"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "ticket_no", name="uq_tickets_company_no"),
        Index("ix_tickets_status_priority", "company_id", "status", "priority"),
    )


class TicketMessage(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "ticket_messages"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    author_name: Mapped[str | None] = mapped_column(String(160))
    direction: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")


class ServiceContract(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Recurring service / maintenance contract (AMC)."""

    __tablename__ = "service_contracts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_type: Mapped[str] = mapped_column(String(32), default="maintenance", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    billing_frequency: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    contract_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    annual_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    invoiced_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    visits_included: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    resolution_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    parts_discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    labour_included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    renewal_notice_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=ServiceContractStatus.DRAFT.value, nullable=False, index=True
    )
    signed_by_customer: Mapped[str | None] = mapped_column(String(200))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assets: Mapped[list[ServiceContractAsset]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_service_contracts_company_no"),
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
    )


class ServiceContractAsset(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "service_contract_assets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    serial_number: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(250))
    coverage_notes: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[ServiceContract] = relationship(back_populates="assets")

    __table_args__ = (UniqueConstraint("contract_id", "asset_id", name="uq_service_contract_assets_pair"),)


class WorkOrder(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Field work order: technician, parts, labour and customer sign-off."""

    __tablename__ = "work_orders"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_type: Mapped[str] = mapped_column(
        String(24), default=WorkOrderType.MAINTENANCE.value, nullable=False
    )
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_requests.id", ondelete="SET NULL")
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tickets.id"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("service_contracts.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_orders.id"))

    technician_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    team_ids: Mapped[list | None] = mapped_column(JSONType)
    scheduled_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    travel_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    site_address: Mapped[str | None] = mapped_column(String(400))
    latitude: Mapped[Decimal | None] = mapped_column(Rate)
    longitude: Mapped[Decimal | None] = mapped_column(Rate)

    problem_description: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    technician_notes: Mapped[str | None] = mapped_column(Text)
    customer_signature_name: Mapped[str | None] = mapped_column(String(160))
    customer_signature_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_rating: Mapped[int | None] = mapped_column(Integer)

    labour_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    parts_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    expenses_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    warranty_claim: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    parts: Mapped[list[WorkOrderPart]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderPart.sequence_no"
    )
    labours: Mapped[list[WorkOrderLabor]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderLabor.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_work_orders_company_no"),
        Index("ix_work_orders_status_date", "company_id", "status", "document_date"),
        Index("ix_work_orders_technician", "company_id", "technician_id", "scheduled_date"),
    )


class WorkOrderPart(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "work_order_parts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(400))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    is_issued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_under_warranty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    work_order: Mapped[WorkOrder] = relationship(back_populates="parts")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class WorkOrderLabor(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "work_order_labor"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    technician_name: Mapped[str | None] = mapped_column(String(160))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cost_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    billable_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cost_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    work_order: Mapped[WorkOrder] = relationship(back_populates="labours")

    __table_args__ = (CheckConstraint("hours >= 0", name="hours_non_negative"),)


class Warranty(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Warranty registration for a sold product or installed asset."""

    __tablename__ = "warranties"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warranty_no: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))
    sales_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    warranty_type: Mapped[str] = mapped_column(String(24), default="standard", nullable=False)
    coverage: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    claims_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_claim_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "warranty_no", name="uq_warranties_company_no"),
        Index("ix_warranties_customer", "company_id", "customer_id", "end_date"),
    )


class TechnicianSchedule(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Planned technician availability / dispatching slot."""

    __tablename__ = "technician_schedules"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_orders.id"))
    skills: Mapped[list | None] = mapped_column(JSONType)
    notes: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (Index("ix_technician_schedules_date", "company_id", "schedule_date", "employee_id"),)
