"""Inventory models: immutable stock ledger, balances, batches, serials,
transfers, adjustments and stock counts."""

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

from app.core.enums import DocumentStatus, MovementType
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Quantity,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Batch(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Batch / lot with optional expiry (required for pharmaceuticals, food...)."""

    __tablename__ = "batches"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_number: Mapped[str] = mapped_column(String(64), nullable=False)
    lot_number: Mapped[str | None] = mapped_column(String(64))
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    country_of_origin: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", "batch_number", name="uq_batches_product_number"),
    )


class SerialNumber(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "serial_numbers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouse_locations.id"))
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False, index=True)
    reference_type: Mapped[str | None] = mapped_column(String(48))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "product_id", "serial_number", name="uq_serials_product_number"),)


class StockLedgerEntry(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Append-only stock ledger.

    Every inventory mutation writes exactly one row.  ``balance_quantity`` and
    ``balance_value`` capture the running position for the
    (product, warehouse, batch) key after applying this entry, which makes
    weighted average costing auditable and reproducible.
    """

    __tablename__ = "stock_ledger_entries"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(4), default="in", nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouse_locations.id", ondelete="SET NULL")
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    serial_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("serial_numbers.id"))
    balance_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    balance_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    reference_type: Mapped[str | None] = mapped_column(String(48), index=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    reference_no: Mapped[str | None] = mapped_column(String(64))
    reference_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    party_type: Mapped[str | None] = mapped_column(String(16))
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_stock_ledger_product_wh", "company_id", "product_id", "warehouse_id", "entry_date"),
        Index("ix_stock_ledger_reference", "company_id", "reference_type", "reference_id"),
    )


class StockBalance(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Current position per product / warehouse / batch (updated atomically
    together with the ledger entry inside the same transaction)."""

    __tablename__ = "stock_balances"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    reserved_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    incoming_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    last_movement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reorder_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def available_quantity(self) -> Decimal:
        return Decimal(self.quantity or 0) - Decimal(self.reserved_quantity or 0)

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", "warehouse_id", "batch_id", name="uq_stock_balances_scope"),
        Index("ix_stock_balances_company_product", "company_id", "product_id"),
    )


class StockTransfer(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "stock_transfers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    source_branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    destination_branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    lines: Mapped[list[StockTransferLine]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan", order_by="StockTransferLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_stock_transfers_company_no"),)


class StockTransferLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "stock_transfer_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    serial_numbers: Mapped[list | None] = mapped_column(JSONType)
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(String(250))

    transfer: Mapped[StockTransfer] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class StockAdjustment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Adjustment / opening balance document.  ``adjustment_type`` distinguishes
    physical count corrections, scrap write-offs and opening balances."""

    __tablename__ = "stock_adjustments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    adjustment_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    adjustment_type: Mapped[str] = mapped_column(String(24), default="increase", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(250))
    offset_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    lines: Mapped[list[StockAdjustmentLine]] = relationship(
        back_populates="adjustment", cascade="all, delete-orphan", order_by="StockAdjustmentLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_stock_adjustments_company_no"),)


class StockAdjustmentLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "stock_adjustment_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_adjustments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), default="in", nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    serial_numbers: Mapped[list | None] = mapped_column(JSONType)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouse_locations.id"))
    notes: Mapped[str | None] = mapped_column(String(250))

    adjustment: Mapped[StockAdjustment] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("direction IN ('in','out')", name="direction_valid"),
    )


class StockCount(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Physical stocktake session."""

    __tablename__ = "stock_counts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouse_zones.id"))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    count_type: Mapped[str] = mapped_column(String(24), default="full", nullable=False)
    adjustment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stock_adjustments.id"))
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[StockCountLine]] = relationship(
        back_populates="stock_count", cascade="all, delete-orphan", order_by="StockCountLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_stock_counts_company_no"),)


class StockCountLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "stock_count_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_count_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_counts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouse_locations.id"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    system_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    counted_quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    variance_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    variance_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_counted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(250))

    stock_count: Mapped[StockCount] = relationship(back_populates="lines")


class InventoryValuationLayer(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Cost layer used by FIFO valuation and costing traceability."""

    __tablename__ = "inventory_valuation_layers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    layer_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    source_ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_ledger_entries.id", ondelete="SET NULL")
    )
    is_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_inventory_layers_fifo", "company_id", "product_id", "warehouse_id", "layer_date"),
        CheckConstraint("remaining_quantity >= 0", name="remaining_non_negative"),
    )


class ReorderRule(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Per warehouse reorder policy overriding the product defaults."""

    __tablename__ = "reorder_rules"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    reorder_level: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    reorder_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    max_level: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    preferred_supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "product_id", "warehouse_id", name="uq_reorder_rules_scope"),)


class StockMovementTemplate(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Default account mapping per movement type (inventory <-> accounting)."""

    __tablename__ = "stock_movement_templates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    debit_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    credit_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "movement_type", name="uq_stock_movement_templates_type"),)


DEFAULT_MOVEMENT_TYPES = tuple(member.value for member in MovementType)
