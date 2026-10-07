"""Fixed assets: categories, register, depreciation, transfers, disposal."""

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

from app.core.enums import AssetStatus, DepreciationMethod, DocumentStatus
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


class AssetCategory(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "asset_categories"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    depreciation_method: Mapped[str] = mapped_column(
        String(24), default=DepreciationMethod.STRAIGHT_LINE.value, nullable=False
    )
    useful_life_years: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    salvage_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    declining_rate: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    asset_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    depreciation_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    accumulated_depreciation_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id")
    )
    disposal_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_asset_categories_company_code"),
        CheckConstraint("useful_life_years >= 0", name="useful_life_non_negative"),
    )


class Asset(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "assets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_no: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_categories.id", ondelete="SET NULL")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    barcode: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(160))
    year_of_manufacture: Mapped[int | None] = mapped_column(Integer)

    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    location: Mapped[str | None] = mapped_column(String(250))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    custodian_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    purchase_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_invoices.id")
    )

    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    in_service_date: Mapped[date | None] = mapped_column(Date)
    acquisition_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    additional_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))

    depreciation_method: Mapped[str] = mapped_column(
        String(24), default=DepreciationMethod.STRAIGHT_LINE.value, nullable=False
    )
    useful_life_years: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declining_rate: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    total_units_expected: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    book_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    last_depreciation_date: Mapped[date | None] = mapped_column(Date)
    depreciation_start_date: Mapped[date | None] = mapped_column(Date)

    asset_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    depreciation_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    accumulated_depreciation_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id")
    )

    status: Mapped[str] = mapped_column(String(24), default=AssetStatus.DRAFT.value, nullable=False, index=True)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    insurance_policy_no: Mapped[str | None] = mapped_column(String(120))
    insurance_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    insurance_expiry: Mapped[date | None] = mapped_column(Date)
    disposal_date: Mapped[date | None] = mapped_column(Date)
    disposal_proceeds: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    disposal_reason: Mapped[str | None] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    depreciation_entries: Mapped[list[AssetDepreciation]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    @property
    def depreciable_amount(self) -> Decimal:
        return Decimal(self.total_cost or 0) - Decimal(self.salvage_value or 0)

    __table_args__ = (
        UniqueConstraint("company_id", "asset_no", name="uq_assets_company_no"),
        CheckConstraint("acquisition_cost >= 0", name="cost_non_negative"),
        Index("ix_assets_company_status", "company_id", "status"),
    )


class AssetDepreciation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """One row per depreciation run (schedule line + posting)."""

    __tablename__ = "asset_depreciations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_date: Mapped[date] = mapped_column(Date, nullable=False)
    opening_book_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    depreciation_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    closing_book_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    units_produced: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    method: Mapped[str] = mapped_column(String(24), default=DepreciationMethod.STRAIGHT_LINE.value, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(400))

    asset: Mapped[Asset] = relationship(back_populates="depreciation_entries")

    __table_args__ = (
        UniqueConstraint("asset_id", "period_year", "period_month", name="uq_asset_depreciations_period"),
        CheckConstraint("depreciation_amount >= 0", name="amount_non_negative"),
        Index("ix_asset_depreciations_date", "company_id", "depreciation_date"),
    )


class AssetTransfer(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "asset_transfers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    to_branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    from_employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    to_employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    from_location: Mapped[str | None] = mapped_column(String(250))
    to_location: Mapped[str | None] = mapped_column(String(250))
    from_cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    to_cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    reason: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_name: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_asset_transfers_company_no"),)


class AssetDisposal(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "asset_disposals"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    disposal_date: Mapped[date] = mapped_column(Date, nullable=False)
    disposal_type: Mapped[str] = mapped_column(String(24), default="sale", nullable=False)
    proceeds_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    removal_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    net_book_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gain_loss_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gain_loss_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_asset_disposals_company_no"),)


class AssetMaintenance(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "asset_maintenance"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    maintenance_type: Mapped[str] = mapped_column(String(24), default="preventive", nullable=False)
    reported_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    completed_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[str | None] = mapped_column(String(200))
    technician_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    parts_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    other_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    downtime_hours: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_asset_maintenance_company_no"),)
