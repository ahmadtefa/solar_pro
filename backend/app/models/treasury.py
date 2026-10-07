"""Cash, banks, payments, receipts, transfers, cheques and bank reconciliation."""

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
    BankReconciliationStatus,
    CashFlowCategory,
    DocumentStatus,
    PartyType,
    PaymentDirection,
    PaymentMethod,
)
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class CashAccount(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "cash_accounts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    custodian_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cash_limit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_cash_accounts_company_code"),)


class BankAccount(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "bank_accounts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    branch_name: Mapped[str | None] = mapped_column(String(160))
    account_number: Mapped[str | None] = mapped_column(String(64))
    iban: Mapped[str | None] = mapped_column(String(64))
    swift_code: Mapped[str | None] = mapped_column(String(24))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    currency_code: Mapped[str | None] = mapped_column(String(3))
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    overdraft_limit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    signatories: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_bank_accounts_company_code"),)


class Payment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Cash / bank payment or receipt voucher.

    ``direction`` distinguishes inbound (receipt from a customer) from outbound
    (payment to a supplier), keeping a single settlement engine for both sides.
    """

    __tablename__ = "payments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default=PaymentDirection.INBOUND.value, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), default=PaymentMethod.CASH.value, nullable=False)
    party_type: Mapped[str] = mapped_column(String(16), default=PartyType.CUSTOMER.value, nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    party_name: Mapped[str | None] = mapped_column(String(200))

    cash_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cash_accounts.id"))
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"))
    payment_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id"), comment="Account used when settling against a specific GL account"
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))

    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    unallocated_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    withholds_tax: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    withholding_tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    withholding_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    cheque_number: Mapped[str | None] = mapped_column(String(64))
    cheque_date: Mapped[date | None] = mapped_column(Date)
    card_reference: Mapped[str | None] = mapped_column(String(80))

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_payments_company_no"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_party_date", "company_id", "party_type", "party_id", "document_date"),
        Index("ix_payments_status", "company_id", "status", "document_date"),
    )


class PaymentAllocation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Applies a payment to one or more invoices (partial settlement)."""

    __tablename__ = "payment_allocations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    target_document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    target_document_no: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    write_off_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="allocations")

    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)


class TreasuryTransfer(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Transfer between two treasury accounts (cash -> bank, bank -> bank)."""

    __tablename__ = "treasury_transfers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_cash_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cash_accounts.id"))
    to_cash_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cash_accounts.id"))
    from_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"))
    to_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    charges: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_treasury_transfers_company_no"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )


class Cheque(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Post-dated cheque register (issued or received)."""

    __tablename__ = "cheques"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cheque_number: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default=PaymentDirection.INBOUND.value, nullable=False)
    party_type: Mapped[str | None] = mapped_column(String(16))
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    deposited_at: Mapped[date | None] = mapped_column(Date)
    cleared_at: Mapped[date | None] = mapped_column(Date)
    bounced_reason: Mapped[str | None] = mapped_column(String(400))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("company_id", "cheque_number", "direction", name="uq_cheques_number_direction"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_cheques_due_date", "company_id", "due_date", "status"),
    )


class BankReconciliation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "bank_reconciliations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    statement_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=BankReconciliationStatus.DRAFT.value, nullable=False
    )
    reconciled_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list[BankReconciliationLine]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_bank_reconciliations_company_no"),)


class BankReconciliationLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "bank_reconciliation_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bank_reconciliations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    journal_entry_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entry_lines.id")
    )
    statement_reference: Mapped[str | None] = mapped_column(String(120))
    transaction_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="credit", nullable=False)
    is_matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_outstanding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(400))

    reconciliation: Mapped[BankReconciliation] = relationship(back_populates="lines")


class CashFlowSnapshot(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Materialised cash position per account and day (fast dashboards)."""

    __tablename__ = "cash_flow_snapshots"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_kind: Mapped[str] = mapped_column(String(16), default="cash", nullable=False)
    cash_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cash_accounts.id"))
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"))
    inflow: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    outflow: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cash_flow_category: Mapped[str] = mapped_column(
        String(16), default=CashFlowCategory.OPERATING.value, nullable=False
    )

    __table_args__ = (Index("ix_cash_flow_snapshots_date", "company_id", "snapshot_date"),)


class CurrencyRevaluation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """FX gain/loss run for foreign currency balances."""

    __tablename__ = "currency_revaluations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    revaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    old_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    new_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    foreign_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gain_loss_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    gain_loss_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    fx_rate_used_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "document_no", name="uq_currency_revaluations_company_no"),)
