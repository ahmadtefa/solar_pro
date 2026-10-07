"""CRM: lead sources, pipeline stages, leads, opportunities and activities."""

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
    ActivityStatus,
    ActivityType,
    LeadStatus,
    OpportunityStage,
    Priority,
)
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class LeadSource(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "lead_sources"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    channel: Mapped[str | None] = mapped_column(String(48))
    cost_per_lead: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_lead_sources_company_code"),)


class PipelineStage(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Configurable sales/CRM pipeline stage (extensible to future pipelines)."""

    __tablename__ = "pipeline_stages"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline: Mapped[str] = mapped_column(String(48), default="sales", nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    sequence_no: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    probability: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    color: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "pipeline", "code", name="uq_pipeline_stages_scope"),)


class Lead(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "leads"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_no: Mapped[str] = mapped_column(String(64), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(40))
    mobile: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(300))
    industry: Mapped[str | None] = mapped_column(String(80))

    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("lead_sources.id"))
    stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"))
    status: Mapped[str] = mapped_column(String(24), default=LeadStatus.NEW.value, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    campaign: Mapped[str | None] = mapped_column(String(120))

    expected_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interest: Mapped[str | None] = mapped_column(String(250))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    converted_customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    converted_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lost_reason: Mapped[str | None] = mapped_column(String(400))
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="lead")
    activities: Mapped[list[Activity]] = relationship(
        back_populates="lead", foreign_keys="Activity.lead_id", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "lead_no", name="uq_leads_company_no"),
        Index("ix_leads_company_status", "company_id", "status"),
        Index("ix_leads_owner", "company_id", "owner_id"),
    )


class Opportunity(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "opportunities"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_no: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"))
    stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("pipeline_stages.id"))
    stage: Mapped[str] = mapped_column(String(24), default=OpportunityStage.NEW.value, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))

    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    weighted_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    probability: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    actual_close_date: Mapped[date | None] = mapped_column(Date)
    stage_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lost_reason: Mapped[str | None] = mapped_column(String(400))
    competitor: Mapped[str | None] = mapped_column(String(200))
    next_step: Mapped[str | None] = mapped_column(String(250))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)

    lead: Mapped[Lead | None] = relationship(back_populates="opportunities")
    activities: Mapped[list[Activity]] = relationship(
        back_populates="opportunity", foreign_keys="Activity.opportunity_id", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "opportunity_no", name="uq_opportunities_company_no"),
        Index("ix_opportunities_stage", "company_id", "stage"),
        Index("ix_opportunities_owner", "company_id", "owner_id"),
    )


class Activity(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Call / meeting / task / follow-up, reusable across every module."""

    __tablename__ = "activities"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(24), default=ActivityType.CALL.value, nullable=False)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=ActivityStatus.PLANNED.value, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.NORMAL.value, nullable=False)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))

    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(250))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(120))
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    lead: Mapped[Lead | None] = relationship(back_populates="activities", foreign_keys=[lead_id])
    opportunity: Mapped[Opportunity | None] = relationship(back_populates="activities", foreign_keys=[opportunity_id])

    __table_args__ = (
        Index("ix_activities_owner_due", "company_id", "owner_id", "due_date"),
        Index("ix_activities_entity", "company_id", "entity_type", "entity_id"),
        CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 0", name="duration_non_negative"),
    )


class LostReason(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Configurable win/loss reasons for analytics."""

    __tablename__ = "lost_reasons"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    is_won_reason: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_lost_reasons_company_code"),)


class SalesTarget(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Sales targets powering the sales dashboard."""

    __tablename__ = "sales_targets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    period_type: Mapped[str] = mapped_column(String(16), default="month", nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    achieved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    target_quantity: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    commission_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (
        Index("ix_sales_targets_period", "company_id", "period_start", "period_end"),
    )
