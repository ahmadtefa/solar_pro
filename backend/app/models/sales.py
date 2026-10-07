"""Sales module: quotations, orders, deliveries, invoices, credit notes and POS."""

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

from app.core.enums import DocumentStatus, PaymentMethod, ShiftStatus
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
from app.models.mixins import (
    DocumentHeaderMixin,
    DocumentLineMixin,
    QuantityStatusMixin,
    QuantityTrackingMixin,
)


# --------------------------------------------------------------------------- #
# Quotation
# --------------------------------------------------------------------------- #
class Quotation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "quotations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("contacts.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("opportunities.id"))
    valid_until: Mapped[date | None] = mapped_column(Date)
    converted_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    lines: Mapped[list[QuotationLine]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_quotations_company_no"),
        Index("ix_quotations_customer_date", "company_id", "customer_id", "document_date"),
    )


class QuotationLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin, QuantityTrackingMixin):
    __tablename__ = "quotation_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    quotation: Mapped[Quotation] = relationship(back_populates="lines")


# --------------------------------------------------------------------------- #
# Sales order
# --------------------------------------------------------------------------- #
class SalesOrder(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin, QuantityStatusMixin):
    __tablename__ = "sales_orders"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("quotations.id", ondelete="SET NULL")
    )
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    commission_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    credit_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credit_check_notes: Mapped[str | None] = mapped_column(String(400))

    lines: Mapped[list[SalesOrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_sales_orders_company_no"),
        Index("ix_sales_orders_customer_date", "company_id", "customer_id", "document_date"),
        Index("ix_sales_orders_status", "company_id", "status", "document_date"),
    )


class SalesOrderLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin, QuantityTrackingMixin):
    __tablename__ = "sales_order_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order: Mapped[SalesOrder] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_non_negative"),)


# --------------------------------------------------------------------------- #
# Delivery note
# --------------------------------------------------------------------------- #
class DeliveryNote(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "delivery_notes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL")
    )
    delivery_address: Mapped[str | None] = mapped_column(String(400))
    driver_name: Mapped[str | None] = mapped_column(String(120))
    vehicle_number: Mapped[str | None] = mapped_column(String(64))
    received_by_name: Mapped[str | None] = mapped_column(String(160))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    lines: Mapped[list[DeliveryNoteLine]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan", order_by="DeliveryNoteLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_delivery_notes_company_no"),)


class DeliveryNoteLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "delivery_note_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_order_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_order_lines.id"))

    delivery: Mapped[DeliveryNote] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


# --------------------------------------------------------------------------- #
# Sales invoice
# --------------------------------------------------------------------------- #
class SalesInvoice(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "sales_invoices"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL")
    )
    delivery_note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_notes.id", ondelete="SET NULL")
    )
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    sales_channel: Mapped[str] = mapped_column(String(24), default="direct", nullable=False)
    commission_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    #: COGS booked with the invoice (kept for traceability of the posting)
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # POS linkage
    pos_shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("pos_shifts.id"))
    pos_terminal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("pos_terminals.id"))

    is_return: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    returned_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    return_reason: Mapped[str | None] = mapped_column(String(400))
    e_invoice_uuid: Mapped[str | None] = mapped_column(String(120))
    e_invoice_status: Mapped[str | None] = mapped_column(String(32))

    lines: Mapped[list[SalesInvoiceLine]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="SalesInvoiceLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_sales_invoices_company_no"),
        Index("ix_sales_invoices_customer_date", "company_id", "customer_id", "document_date"),
        Index("ix_sales_invoices_status", "company_id", "status", "document_date"),
    )


class SalesInvoiceLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "sales_invoice_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_order_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_order_lines.id"))
    delivery_note_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_note_lines.id")
    )
    revenue_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    cogs_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))

    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_non_negative"),)


class CreditNote(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Sales return / credit note."""

    __tablename__ = "credit_notes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    return_reason: Mapped[str | None] = mapped_column(String(400))
    is_inventory_returned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    refund_method: Mapped[str | None] = mapped_column(String(24))

    lines: Mapped[list[CreditNoteLine]] = relationship(
        back_populates="credit_note", cascade="all, delete-orphan", order_by="CreditNoteLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_credit_notes_company_no"),)


class CreditNoteLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "credit_note_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoice_lines.id"))

    credit_note: Mapped[CreditNote] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class SalesCommission(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Salesperson commission accrual and settlement."""

    __tablename__ = "sales_commissions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salesperson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_invoices.id"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    commission_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_sales_commissions_period", "company_id", "salesperson_id", "period_start"),)


# --------------------------------------------------------------------------- #
# POS
# --------------------------------------------------------------------------- #
class PosTerminal(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "pos_terminals"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    cash_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cash_accounts.id"))
    default_customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("price_lists.id"))
    receipt_printer: Mapped[str | None] = mapped_column(String(120))
    receipt_footer: Mapped[str | None] = mapped_column(Text)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_discount: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("100"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_pos_terminals_company_code"),)


class PosShift(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Cashier shift with cash reconciliation."""

    __tablename__ = "pos_shifts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_no: Mapped[str] = mapped_column(String(64), nullable=False)
    terminal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pos_terminals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opening_cash: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    expected_cash: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    counted_cash: Mapped[Decimal | None] = mapped_column(Money)
    cash_difference: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_sales: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_cash_sales: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_card_sales: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_wallet_sales: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_returns: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_discounts: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    invoice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ShiftStatus.OPEN.value, nullable=False)
    difference_reason: Mapped[str | None] = mapped_column(String(400))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    z_report_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "shift_no", name="uq_pos_shifts_company_no"),
        Index("ix_pos_shifts_cashier_status", "company_id", "cashier_id", "status"),
    )


class PosCashMovement(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Cash drop / pickup / petty cash inside a shift."""

    __tablename__ = "pos_cash_movements"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pos_shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)  # cash_in | cash_out | drop | pickup
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(250))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))

    __table_args__ = (CheckConstraint("amount <> 0", name="amount_not_zero"),)


class PosPayment(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Split payment line for a POS invoice."""

    __tablename__ = "pos_payments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("pos_shifts.id"))
    payment_method: Mapped[str] = mapped_column(String(24), default=PaymentMethod.CASH.value, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tendered_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    change_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    card_type: Mapped[str | None] = mapped_column(String(40))
    terminal_reference: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)
