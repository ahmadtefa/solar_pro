"""Declarative mixins shared by the transactional documents.

Using mixins keeps every document header/line structurally identical, which is
what allows the generic workflow, printing, reporting and import/export
services to work across all modules without special cases.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DocumentStatus, PaymentStatus
from app.models.base import JSONType, Money, Percent, Quantity, Rate


class DocumentHeaderMixin:
    """Common columns of every business document header."""

    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(24), default=PaymentStatus.UNPAID.value, nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    other_charges: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    shipping_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_amount_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    terms_and_conditions: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(120))
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(400))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(400))

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    print_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DocumentLineMixin:
    """Common columns of every business document line."""

    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(String(500))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    tax_rate: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouse_locations.id"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("batches.id"))
    serial_numbers: Mapped[list | None] = mapped_column(JSONType)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class QuantityTrackingMixin:
    """Fulfilment progress columns used by orders (received / delivered / billed)."""

    ordered_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    fulfilled_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    invoiced_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)


class AmountTrackingMixin:
    """Fulfilment progress for amounts."""

    ordered_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    fulfilled_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    invoiced_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remaining_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)


class QuantityStatusMixin:
    """Aggregated status flags for order headers."""

    is_fully_received: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fully_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fully_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fully_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


#: Re-exported for convenience in model modules.
__all__ = [
    "AmountTrackingMixin",
    "DocumentHeaderMixin",
    "DocumentLineMixin",
    "Numeric",
    "QuantityStatusMixin",
    "QuantityTrackingMixin",
]
