"""Purchasing module: requests, RFQs, quotations, orders, receipts, invoices."""

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

from app.core.enums import DocumentStatus
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    Quantity,
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


class PurchaseRequest(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "purchase_requests"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    required_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))

    lines: Mapped[list[PurchaseRequestLine]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="PurchaseRequestLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_purchase_requests_company_no"),)


class PurchaseRequestLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "purchase_request_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suggested_supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    required_date: Mapped[date | None] = mapped_column(Date)
    approved_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ordered_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)

    request: Mapped[PurchaseRequest] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class Rfq(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Request for quotation sent to one or more suppliers."""

    __tablename__ = "rfqs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="SET NULL")
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    closing_date: Mapped[date | None] = mapped_column(Date)
    awarded_quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="SET NULL")
    )
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[RfqLine]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", order_by="RfqLine.sequence_no"
    )
    supplier_quotations: Mapped[list[SupplierQuotation]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", foreign_keys="SupplierQuotation.rfq_id"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_rfqs_company_no"),)


class RfqLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "rfq_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_date: Mapped[date | None] = mapped_column(Date)

    rfq: Mapped[Rfq] = relationship(back_populates="lines")


class RfqSupplier(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Supplier invited to quote for an RFQ."""

    __tablename__ = "rfq_suppliers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id", name="uq_rfq_suppliers_pair"),)


class SupplierQuotation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "supplier_quotations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rfqs.id", ondelete="SET NULL"))
    supplier_reference: Mapped[str | None] = mapped_column(String(120))
    valid_until: Mapped[date | None] = mapped_column(Date)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selection_notes: Mapped[str | None] = mapped_column(Text)
    converted_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    lines: Mapped[list[SupplierQuotationLine]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="SupplierQuotationLine.sequence_no"
    )
    rfq: Mapped[Rfq | None] = relationship(back_populates="supplier_quotations", foreign_keys=[rfq_id])

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_supplier_quotations_company_no"),)


class SupplierQuotationLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "supplier_quotation_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    quotation: Mapped[SupplierQuotation] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class PurchaseOrder(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin, QuantityStatusMixin):
    __tablename__ = "purchase_orders"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="SET NULL")
    )
    purchase_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="SET NULL")
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    supplier_reference: Mapped[str | None] = mapped_column(String(120))
    expected_date: Mapped[date | None] = mapped_column(Date)

    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PurchaseOrderLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_purchase_orders_company_no"),
        Index("ix_purchase_orders_supplier_date", "company_id", "supplier_id", "document_date"),
        Index("ix_purchase_orders_status", "company_id", "status", "document_date"),
    )


class PurchaseOrderLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin, QuantityTrackingMixin):
    __tablename__ = "purchase_order_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_request_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_request_lines.id")
    )

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class GoodsReceipt(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Goods receipt note - the document that moves stock."""

    __tablename__ = "goods_receipts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )
    supplier_delivery_note: Mapped[str | None] = mapped_column(String(120))
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    inspected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    inspection_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    inspection_notes: Mapped[str | None] = mapped_column(Text)
    is_invoiced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", order_by="GoodsReceiptLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_goods_receipts_company_no"),)


class GoodsReceiptLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "goods_receipt_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_order_lines.id")
    )
    rejected_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(400))
    batch_number: Mapped[str | None] = mapped_column(String(64))
    expiry_date: Mapped[date | None] = mapped_column(Date)

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class PurchaseInvoice(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    __tablename__ = "purchase_invoices"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="SET NULL")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    supplier_invoice_no: Mapped[str | None] = mapped_column(String(120))
    supplier_invoice_date: Mapped[date | None] = mapped_column(Date)
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    withholding_tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_return: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lines: Mapped[list[PurchaseInvoiceLine]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="PurchaseInvoiceLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_purchase_invoices_company_no"),
        Index("ix_purchase_invoices_supplier_date", "company_id", "supplier_id", "document_date"),
    )


class PurchaseInvoiceLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "purchase_invoice_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_order_lines.id")
    )
    goods_receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipt_lines.id")
    )
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))

    invoice: Mapped[PurchaseInvoice] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class DebitNote(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Purchase return / debit note to a supplier."""

    __tablename__ = "debit_notes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purchase_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_invoices.id", ondelete="SET NULL")
    )
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="SET NULL")
    )
    return_reason: Mapped[str | None] = mapped_column(String(400))
    is_inventory_returned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lines: Mapped[list[DebitNoteLine]] = relationship(
        back_populates="debit_note", cascade="all, delete-orphan", order_by="DebitNoteLine.sequence_no"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_debit_notes_company_no"),)


class DebitNoteLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "debit_note_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    debit_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("debit_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_invoice_lines.id")
    )

    debit_note: Mapped[DebitNote] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class SupplierEvaluation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Supplier scorecard used by the procurement dashboard."""

    __tablename__ = "supplier_evaluations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    quality_score: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    delivery_score: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    price_score: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    service_score: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    evaluated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    comments: Mapped[str | None] = mapped_column(Text)
