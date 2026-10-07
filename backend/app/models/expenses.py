"""Expense management: categories, expense documents, claims and advances."""

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
    Money,
    Percent,
    Quantity,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.models.mixins import DocumentHeaderMixin, DocumentLineMixin


class ExpenseCategory(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "expense_categories"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL")
    )
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    payable_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    default_tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    requires_receipt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_cost_center: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_project: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_threshold: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_expense_categories_company_code"),)


class Expense(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped, DocumentHeaderMixin):
    """Company or employee expense document."""

    __tablename__ = "expenses"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL")
    )
    expense_type: Mapped[str] = mapped_column(String(16), default="company", nullable=False)
    payee_type: Mapped[str | None] = mapped_column(String(16))
    payee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payee_name: Mapped[str | None] = mapped_column(String(200))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("employees.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("expense_claims.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"))
    supplier_invoice_no: Mapped[str | None] = mapped_column(String(120))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[ExpenseLine]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseLine.sequence_no"
    )
    claim: Mapped[ExpenseClaim | None] = relationship(
        "ExpenseClaim", back_populates="expenses", foreign_keys=[claim_id]
    )

    __table_args__ = (
        UniqueConstraint("company_id", "document_no", name="uq_expenses_company_no"),
        Index("ix_expenses_date", "company_id", "document_date"),
        Index("ix_expenses_status", "company_id", "status"),
    )


class ExpenseLine(Base, UUIDMixin, TimestampMixin, CompanyScoped, DocumentLineMixin):
    __tablename__ = "expense_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL")
    )
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    tax_recoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    receipt_reference: Mapped[str | None] = mapped_column(String(120))
    mileage_km: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)

    expense: Mapped[Expense] = relationship(back_populates="lines")


class ExpenseClaim(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Employee reimbursement claim aggregating several expense documents."""

    __tablename__ = "expense_claims"

    @property
    def document_date(self) -> object:
        """Uniform document interface: the business date of this record."""
        return self.claim_date

    @property
    def document_no(self) -> str:
        """Uniform document interface: this record's natural number."""
        return self.claim_no

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_no: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(400))
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    approved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(String(400))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    expenses: Mapped[list[Expense]] = relationship(
        "Expense", back_populates="claim", foreign_keys="Expense.claim_id"
    )

    __table_args__ = (UniqueConstraint("company_id", "claim_no", name="uq_expense_claims_company_no"),)


class ExpenseAdvance(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Cash advance paid to an employee, later settled against claims."""

    __tablename__ = "expense_advances"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    advance_no: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    advance_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    settled_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT.value, nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payments.id"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("journal_entries.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("company_id", "advance_no", name="uq_expense_advances_company_no"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )


class Budget(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Budget by account / cost center / project used for commitment control."""

    __tablename__ = "budgets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("fiscal_years.id"))
    scope_type: Mapped[str] = mapped_column(String(24), default="company", nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    committed_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list[BudgetLine]] = relationship(back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_budgets_company_code"),)


class BudgetLine(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "budget_lines"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"))
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int | None] = mapped_column(Integer)
    budget_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    committed_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    variance_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(400))

    budget: Mapped[Budget] = relationship(back_populates="lines")

    __table_args__ = (Index("ix_budget_lines_lookup", "company_id", "period_year", "period_month"),)
