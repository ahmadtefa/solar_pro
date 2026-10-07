"""Double entry accounting engine models."""

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

from app.core.enums import AccountType, CashFlowCategory, DocumentStatus, NormalBalance, PartyType
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Account(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Chart of accounts node.  Supports unlimited depth via ``parent_id``."""

    __tablename__ = "accounts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(16), default=AccountType.ASSET.value, nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(8), default=NormalBalance.DEBIT.value, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    path: Mapped[str | None] = mapped_column(String(500))
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_manual_entries: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_cost_center: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_party: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    party_type: Mapped[str | None] = mapped_column(String(16))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    cash_flow_category: Mapped[str | None] = mapped_column(String(16))
    is_cash_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_bank_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_control_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_tax_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    opening_balance_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_accounts_company_code"),
        CheckConstraint("level >= 1", name="level_positive"),
        Index("ix_accounts_company_type", "company_id", "account_type"),
        Index("ix_accounts_company_active", "company_id", "is_active"),
    )


class JournalEntry(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Journal voucher header.  Posted entries are immutable."""

    __tablename__ = "journal_entries"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_no: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fiscal_periods.id", ondelete="SET NULL")
    )
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fiscal_years.id", ondelete="SET NULL")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    entry_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    source_document_type: Mapped[str | None] = mapped_column(String(48), index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    source_document_no: Mapped[str | None] = mapped_column(String(64))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)

    total_debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_debit_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_credit_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.DRAFT.value, nullable=False, index=True)
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversed_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entries.id", ondelete="SET NULL")
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(250))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    lines: Mapped[list[JournalEntryLine]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="JournalEntryLine.sequence_no"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "entry_no", name="uq_journal_entries_company_no"),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        Index("ix_journal_entries_company_date", "company_id", "entry_date"),
        Index("ix_journal_entries_company_status", "company_id", "status"),
    )


class JournalEntryLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "journal_entry_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(String(250))
    debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    debit_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)

    # accounting dimensions
    party_type: Mapped[str | None] = mapped_column(String(16))
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("warehouses.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    source_document_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reconciliation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="amounts_non_negative"),
        CheckConstraint("NOT (debit > 0 AND credit > 0)", name="single_sided_line"),
        Index("ix_journal_entry_lines_account_date", "company_id", "account_id"),
        Index("ix_journal_entry_lines_party", "company_id", "party_type", "party_id"),
    )


class PostingRule(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Configurable rule mapping documents to accounts.

    ``account_source`` is a dot path resolved at posting time, e.g.
    ``customer.receivable_account``, ``product.inventory_account``,
    ``tax.purchase_account`` or ``system.cogs_account``.  Resolvers fall back to
    the company default accounts, keeping posting fully data driven instead of
    hardcoded in the service layer.
    """

    __tablename__ = "posting_rules"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(24), default="post", nullable=False)
    line_role: Mapped[str] = mapped_column(String(48), nullable=False)
    account_source: Mapped[str] = mapped_column(String(120), nullable=False)
    fallback_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    entry_side: Mapped[str] = mapped_column(String(8), default="auto", nullable=False)
    amount_source: Mapped[str] = mapped_column(String(48), default="line_subtotal", nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    condition_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", "line_role", name="uq_posting_rules_role"),
        CheckConstraint("entry_side IN ('debit','credit','auto')", name="entry_side_valid"),
    )


class AccountingDimensionValue(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Free-form analytical dimension (e.g. region, channel, vehicle)."""

    __tablename__ = "accounting_dimension_values"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension_code: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounting_dimension_values.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "dimension_code", "code", name="uq_dimension_values_scope"),
    )


class CustomerLedgerEntry(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Accounts receivable sub-ledger (one row per customer document)."""

    __tablename__ = "customer_ledger_entries"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_no: Mapped[str | None] = mapped_column(String(64))
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    journal_entry_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    remarks: Mapped[str | None] = mapped_column(String(250))

    __table_args__ = (
        Index("ix_customer_ledger_customer_date", "company_id", "customer_id", "document_date"),
        Index("ix_customer_ledger_open", "company_id", "customer_id", "is_open"),
    )


class SupplierLedgerEntry(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Accounts payable sub-ledger."""

    __tablename__ = "supplier_ledger_entries"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_no: Mapped[str | None] = mapped_column(String(64))
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    journal_entry_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    remarks: Mapped[str | None] = mapped_column(String(250))

    __table_args__ = (
        Index("ix_supplier_ledger_supplier_date", "company_id", "supplier_id", "document_date"),
        Index("ix_supplier_ledger_open", "company_id", "supplier_id", "is_open"),
    )


class LedgerDocumentLink(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Links settlement documents (payments) to the invoices they settle."""

    __tablename__ = "ledger_document_links"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_type: Mapped[str] = mapped_column(String(16), default=PartyType.CUSTOMER.value, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    settlement_document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    settlement_document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    target_document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    __table_args__ = (Index("ix_ledger_document_links_target", "company_id", "target_document_id"),)


class AccountingPeriodClose(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Year-end close record (retained earnings transfer)."""

    __tablename__ = "accounting_period_closes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entries.id", ondelete="SET NULL")
    )
    net_profit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cash_flow_category_default: Mapped[str] = mapped_column(
        String(16), default=CashFlowCategory.OPERATING.value, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
