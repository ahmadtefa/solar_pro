"""Manufacturing: BOMs, routings, work centers, production orders, WIP."""

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

from app.core.enums import DocumentStatus, ProductionStatus
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


class WorkCenter(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "work_centers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    wip_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    overhead_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    capacity_per_day: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    machine_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overhead_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    efficiency_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("100"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_work_centers_company_code"),)


class Bom(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Bill of materials with versioning."""

    __tablename__ = "boms"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    bom_type: Mapped[str] = mapped_column(String(24), default="manufacture", nullable=False)
    routing_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("routings.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    standard_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    expected_yield_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("100"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    lines: Mapped[list[BomLine]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", order_by="BomLine.sequence_no"
    )
    operations: Mapped[list[BomOperation]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", order_by="BomOperation.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", "version", name="uq_boms_code_version"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class BomLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "bom_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("boms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    component_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    scrap_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_substitute: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    substitute_product_ids: Mapped[list | None] = mapped_column(JSONType)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    operation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bom_operations.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    notes: Mapped[str | None] = mapped_column(String(400))

    bom: Mapped[Bom] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class Routing(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "routings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    operations: Mapped[list[RoutingOperation]] = relationship(
        back_populates="routing", cascade="all, delete-orphan", order_by="RoutingOperation.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "code", "version", name="uq_routings_code_version"),)


class RoutingOperation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "routing_operations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    routing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("routings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_centers.id"))
    setup_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    run_minutes_per_unit: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    teardown_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    machine_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    requires_quality_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    routing: Mapped[Routing] = relationship(back_populates="operations")


class BomOperation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "bom_operations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("boms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_centers.id"))
    setup_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    run_minutes_per_unit: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    machine_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_hour_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overhead_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)

    bom: Mapped[Bom] = relationship(back_populates="operations")


class ProductionOrder(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "production_orders"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bom_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("boms.id"))
    routing_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("routings.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    wip_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_orders.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))

    planned_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    produced_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    scrap_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    rework_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))

    planned_start_date: Mapped[date | None] = mapped_column(Date)
    planned_end_date: Mapped[date | None] = mapped_column(Date)
    actual_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(24), default=ProductionStatus.DRAFT.value, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    material_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overhead_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    scrap_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    wip_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    variance_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    supervisor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    materials: Mapped[list[ProductionOrderMaterial]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )
    operations: Mapped[list[ProductionOperation]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan",
        order_by="ProductionOperation.sequence_no",
    )
    outputs: Mapped[list[ProductionOutput]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )

    @property
    def remaining_quantity(self) -> Decimal:
        return Decimal(self.planned_quantity or 0) - Decimal(self.produced_quantity or 0)

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_production_orders_company_no"),
        CheckConstraint("planned_quantity > 0", name="planned_quantity_positive"),
        Index("ix_production_orders_company_status", "company_id", "status", "planned_start_date"),
    )


class ProductionOrderMaterial(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "production_order_materials"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    production_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    planned_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    issued_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    waste_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(400))

    production_order: Mapped[ProductionOrder] = relationship(back_populates="materials")

    __table_args__ = (CheckConstraint("planned_quantity > 0", name="planned_quantity_positive"),)


class ProductionOperation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "production_operations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    production_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_centers.id"))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    planned_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    actual_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    setup_minutes: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    labour_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    machine_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overhead_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    quality_status: Mapped[str | None] = mapped_column(String(24))
    quality_notes: Mapped[str | None] = mapped_column(Text)

    production_order: Mapped[ProductionOrder] = relationship(back_populates="operations")


class ProductionOutput(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Finished / semi-finished goods produced, plus scrap records."""

    __tablename__ = "production_outputs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    production_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    output_type: Mapped[str] = mapped_column(String(16), default="finished", nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    produced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_status: Mapped[str | None] = mapped_column(String(24))
    scrap_reason: Mapped[str | None] = mapped_column(String(400))
    scrap_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    production_order: Mapped[ProductionOrder] = relationship(back_populates="outputs")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class ProductionCostSheet(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Snapshot of the cost build-up of a production order (auditable WIP)."""

    __tablename__ = "production_cost_sheets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    production_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cost_date: Mapped[date] = mapped_column(Date, nullable=False)
    material_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    labour_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    machine_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overhead_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    scrap_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    produced_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))


__all__ = [
    "Bom",
    "BomLine",
    "BomOperation",
    "ProductionCostSheet",
    "ProductionOperation",
    "ProductionOrder",
    "ProductionOrderMaterial",
    "ProductionOutput",
    "Routing",
    "RoutingOperation",
    "WorkCenter",
    "DocumentStatus",
]
