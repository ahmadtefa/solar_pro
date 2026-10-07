"""Double entry posting engine.

Responsibilities
----------------
* Build balanced journal entries from typed line objects.
* Resolve which account to use through configurable :class:`PostingRule` rows,
  so accounting stays data driven (``customer.receivable_account`` -> account).
* Enforce accounting invariants: balanced entry, open fiscal period, postable
  accounts, required dimensions, no edits to posted documents.
* Maintain the customer / supplier sub-ledgers used by ageing and statements.
* Provide unpost and reversal (with automatic reversal entry) for corrections.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccountType,
    AuditAction,
    CashFlowCategory,
    DocumentStatus,
    NormalBalance,
    PartyType,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.accounting import (
    Account,
    CustomerLedgerEntry,
    JournalEntry,
    JournalEntryLine,
    LedgerDocumentLink,
    PostingRule,
    SupplierLedgerEntry,
)
from app.models.platform import FiscalPeriod, FiscalYear
from app.services.audit_service import AuditContext, AuditService
from app.services.numbering_service import NumberingService

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def money(value: Decimal | int | float | str | None) -> Decimal:
    """Quantise a monetary amount to 2 decimals (banker safe rounding)."""
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class EntryLine:
    """A single journal line request."""

    account_id: uuid.UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = None
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    tax_id: uuid.UUID | None = None
    source_document_line_id: uuid.UUID | None = None
    currency_code: str | None = None
    exchange_rate: Decimal = Decimal("1")

    @property
    def amount(self) -> Decimal:
        return money(self.debit or self.credit)


@dataclass(slots=True)
class PostingResult:
    entry: JournalEntry
    created: bool = True


@dataclass(slots=True)
class DocumentPostingContext:
    """Context describing the document being posted to accounting."""

    document_type: str
    document_id: uuid.UUID
    document_no: str
    document_date: date
    description: str | None = None
    branch_id: uuid.UUID | None = None
    currency_code: str | None = None
    exchange_rate: Decimal = Decimal("1")
    extra: dict[str, Any] = field(default_factory=dict)


class PostingService:
    def __init__(self, db: Session, company_id: uuid.UUID, audit: AuditService | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.audit = audit or AuditService(db, AuditContext(company_id=company_id))
        self._account_cache: dict[str, Account] = {}
        self._rule_cache: dict[tuple[str, str], PostingRule] = {}

    # ------------------------------------------------------------------ setup
    def account_by_code(self, code: str) -> Account:
        if code in self._account_cache:
            return self._account_cache[code]
        account = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.code == code)
        ).scalars().first()
        if account is None:
            raise NotFoundError(f"Account with code {code} was not found", account_code=code)
        self._account_cache[code] = account
        return account

    def account_by_id(self, account_id: uuid.UUID) -> Account:
        account = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.id == account_id)
        ).scalars().first()
        if account is None:
            raise NotFoundError("Account not found", account_id=str(account_id))
        return account

    def resolve_account(
        self,
        role: str,
        *,
        document_type: str,
        explicit_account_id: uuid.UUID | None = None,
        fallback_code: str | None = None,
    ) -> Account:
        """Resolve the account for a document line role.

        Resolution order: explicit account on the document line, configured
        posting rule, fallback account code (chart default), otherwise error.
        """
        if explicit_account_id:
            return self.account_by_id(explicit_account_id)

        key = (document_type, role)
        rule = self._rule_cache.get(key)
        if rule is None:
            rule = self.db.execute(
                select(PostingRule).where(
                    PostingRule.company_id == self.company_id,
                    PostingRule.document_type == document_type,
                    PostingRule.line_role == role,
                    PostingRule.is_active.is_(True),
                )
            ).scalars().first()
            if rule is not None:
                self._rule_cache[key] = rule
        if rule is not None:
            resolved = self._resolve_rule_source(rule)
            if resolved is not None:
                return resolved
            if rule.fallback_account_id:
                return self.account_by_id(rule.fallback_account_id)
        if fallback_code:
            return self.account_by_code(fallback_code)
        raise BusinessRuleError(
            f"No account configured for '{role}' of '{document_type}'. Configure a posting rule or company default.",
            role=role,
            document_type=document_type,
        )

    def _resolve_rule_source(self, rule: PostingRule) -> Account | None:
        """Resolve ``account_source`` values such as ``system.ar_account``."""
        source = (rule.account_source or "").strip()
        if not source:
            return None
        if source.startswith("system."):
            code = source.split(".", 1)[1]
            try:
                return self.account_by_code(code)
            except NotFoundError:
                return None
        if source.startswith("code:"):
            try:
                return self.account_by_code(source.split(":", 1)[1])
            except NotFoundError:
                return None
        return None

    def default_account(self, role: str) -> Account | None:
        """Company default account for well-known roles (AR, AP, VAT, COGS...)."""
        defaults = COMPANY_DEFAULT_ACCOUNTS.get(role)
        if not defaults:
            return None
        try:
            return self.account_by_code(defaults)
        except NotFoundError:
            return None

    # --------------------------------------------------------------- postings
    def build_entry(
        self,
        *,
        context: DocumentPostingContext,
        lines: Sequence[EntryLine],
        entry_type: str = "manual",
        reference: str | None = None,
        auto_post: bool = True,
        user_id: uuid.UUID | None = None,
    ) -> JournalEntry:
        if not lines:
            raise BusinessRuleError("A journal entry requires at least two lines")

        total_debit = money(sum((line.debit or Decimal("0")) for line in lines))
        total_credit = money(sum((line.credit or Decimal("0")) for line in lines))
        if total_debit != total_credit:
            raise BusinessRuleError(
                "Journal entry is not balanced: debits and credits differ",
                total_debit=str(total_debit),
                total_credit=str(total_credit),
                difference=str(total_debit - total_credit),
            )
        if total_debit == 0:
            raise BusinessRuleError("Journal entry has no value")

        period, fiscal_year = self.ensure_period(context.document_date)

        entry = JournalEntry(
            company_id=self.company_id,
            entry_no=NumberingService(self.db, self.company_id).next_number("journal_entry"),
            entry_date=context.document_date,
            fiscal_period_id=period.id if period else None,
            fiscal_year_id=fiscal_year.id if fiscal_year else None,
            branch_id=context.branch_id,
            entry_type=entry_type,
            reference=reference or context.document_no,
            description=context.description or f"{context.document_type} {context.document_no}",
            source_document_type=context.document_type,
            source_document_id=context.document_id,
            source_document_no=context.document_no,
            currency_code=context.currency_code,
            exchange_rate=context.exchange_rate or Decimal("1"),
            total_debit=total_debit,
            total_credit=total_credit,
            status=DocumentStatus.DRAFT.value,
            created_by_id=user_id,
        )
        for index, line in enumerate(lines, start=1):
            account = self.account_by_id(line.account_id)
            self._validate_line_account(account, line)
            rate = line.exchange_rate or context.exchange_rate or Decimal("1")
            currency = line.currency_code or context.currency_code
            debit = money(line.debit)
            credit = money(line.credit)
            entry.lines.append(
                JournalEntryLine(
                    company_id=self.company_id,
                    sequence_no=index,
                    account_id=account.id,
                    description=line.description,
                    debit=debit,
                    credit=credit,
                    debit_base=money(debit * rate) if currency else debit,
                    credit_base=money(credit * rate) if currency else credit,
                    currency_code=currency,
                    exchange_rate=rate,
                    party_type=line.party_type,
                    party_id=line.party_id,
                    branch_id=line.branch_id or context.branch_id,
                    department_id=line.department_id,
                    cost_center_id=line.cost_center_id,
                    project_id=line.project_id,
                    warehouse_id=line.warehouse_id,
                    product_id=line.product_id,
                    tax_id=line.tax_id,
                    source_document_line_id=line.source_document_line_id,
                )
            )
        entry.total_debit_base = money(sum(line.debit_base for line in entry.lines))
        entry.total_credit_base = money(sum(line.credit_base for line in entry.lines))
        self.db.add(entry)
        self.db.flush()

        self.audit.record(
            action=AuditAction.CREATE,
            entity_type="journal_entry",
            entity_id=entry.id,
            entity_label=entry.entry_no,
            new_values={"total_debit": str(total_debit), "source": context.document_no},
        )
        if auto_post:
            self.post_entry(entry, user_id=user_id)
        return entry

    def _validate_line_account(self, account: Account, line: EntryLine) -> None:
        if not account.is_postable:
            raise BusinessRuleError(f"Account {account.code} is a group account and cannot be posted to")
        if not account.is_active:
            raise BusinessRuleError(f"Account {account.code} is inactive")
        if account.requires_cost_center and not line.cost_center_id:
            raise BusinessRuleError(f"Account {account.code} requires a cost center")
        if account.requires_party and not line.party_id:
            raise BusinessRuleError(f"Account {account.code} requires a party (customer/supplier)")
        if line.debit and line.credit:
            raise BusinessRuleError("A journal line cannot be both a debit and a credit")
        if not line.debit and not line.credit:
            raise BusinessRuleError("A journal line requires a debit or a credit amount")

    def post_entry(self, entry: JournalEntry, *, user_id: uuid.UUID | None = None) -> JournalEntry:
        if entry.status == DocumentStatus.POSTED.value:
            return entry
        if entry.status in {DocumentStatus.CANCELLED.value, DocumentStatus.REJECTED.value}:
            raise BusinessRuleError("A cancelled or rejected entry cannot be posted")
        if money(entry.total_debit) != money(entry.total_credit):
            raise BusinessRuleError("Cannot post an unbalanced journal entry")

        period = None
        if entry.fiscal_period_id:
            period = self.db.get(FiscalPeriod, entry.fiscal_period_id)
        if period is None:
            period, fiscal_year = self.ensure_period(entry.entry_date)
            if fiscal_year is not None:
                entry.fiscal_year_id = fiscal_year.id
            if period is not None:
                entry.fiscal_period_id = period.id
        if period is not None and period.is_closed:
            raise BusinessRuleError(f"Fiscal period {period.name} is closed for posting")

        entry.status = DocumentStatus.POSTED.value
        entry.posting_date = entry.entry_date
        entry.posted_at = datetime.now(UTC)
        entry.posted_by_id = user_id
        self.db.flush()
        self.audit.record(
            action=AuditAction.POST,
            entity_type="journal_entry",
            entity_id=entry.id,
            entity_label=entry.entry_no,
            remarks=f"Posted {entry.total_debit} debit / {entry.total_credit} credit",
        )
        return entry

    def unpost_entry(self, entry: JournalEntry, *, reason: str, user_id: uuid.UUID | None = None) -> JournalEntry:
        if entry.status != DocumentStatus.POSTED.value:
            raise BusinessRuleError("Only posted entries can be unposted")
        if entry.is_reversal:
            raise BusinessRuleError("Reversal entries cannot be unposted")
        reconciled = self.db.execute(
            select(func.count())
            .select_from(JournalEntryLine)
            .where(JournalEntryLine.entry_id == entry.id, JournalEntryLine.reconciled.is_(True))
        ).scalar_one()
        if reconciled:
            raise BusinessRuleError("This entry contains reconciled lines and cannot be unposted")
        period = self.db.get(FiscalPeriod, entry.fiscal_period_id) if entry.fiscal_period_id else None
        if period is not None and period.is_closed:
            raise BusinessRuleError("The fiscal period is closed; reverse the entry instead")
        entry.status = DocumentStatus.DRAFT.value
        entry.posted_at = None
        entry.posted_by_id = None
        self.db.flush()
        self.audit.record(
            action=AuditAction.UNPOST,
            entity_type="journal_entry",
            entity_id=entry.id,
            entity_label=entry.entry_no,
            remarks=reason,
            new_values={"status": entry.status, "unposted_by": str(user_id) if user_id else None},
        )
        return entry

    def reverse_entry(
        self,
        entry: JournalEntry,
        *,
        reason: str,
        reversal_date: date | None = None,
        user_id: uuid.UUID | None = None,
    ) -> JournalEntry:
        """Create and post a mirror entry, leaving the original untouched."""
        if entry.status != DocumentStatus.POSTED.value:
            raise BusinessRuleError("Only posted entries can be reversed")
        if entry.is_reversal:
            raise BusinessRuleError("A reversal entry cannot itself be reversed")
        reversal = JournalEntry(
            company_id=self.company_id,
            entry_no=NumberingService(self.db, self.company_id).next_number("journal_entry"),
            entry_date=reversal_date or date.today(),
            branch_id=entry.branch_id,
            entry_type="reversal",
            reference=entry.entry_no,
            description=f"Reversal of {entry.entry_no}: {reason}",
            source_document_type=entry.source_document_type,
            source_document_id=entry.source_document_id,
            source_document_no=entry.source_document_no,
            currency_code=entry.currency_code,
            exchange_rate=entry.exchange_rate,
            status=DocumentStatus.DRAFT.value,
            is_reversal=True,
            reversed_entry_id=entry.id,
            reversal_reason=reason,
            created_by_id=user_id,
        )
        for line in entry.lines:
            reversal.lines.append(
                JournalEntryLine(
                    company_id=self.company_id,
                    sequence_no=line.sequence_no,
                    account_id=line.account_id,
                    description=f"Reversal: {line.description or ''}".strip(),
                    debit=line.credit,
                    credit=line.debit,
                    debit_base=line.credit_base,
                    credit_base=line.debit_base,
                    currency_code=line.currency_code,
                    exchange_rate=line.exchange_rate,
                    party_type=line.party_type,
                    party_id=line.party_id,
                    branch_id=line.branch_id,
                    department_id=line.department_id,
                    cost_center_id=line.cost_center_id,
                    project_id=line.project_id,
                    warehouse_id=line.warehouse_id,
                    product_id=line.product_id,
                    tax_id=line.tax_id,
                )
            )
        reversal.total_debit = entry.total_credit
        reversal.total_credit = entry.total_debit
        reversal.total_debit_base = entry.total_credit_base
        reversal.total_credit_base = entry.total_debit_base
        self.db.add(reversal)
        self.db.flush()
        self.post_entry(reversal, user_id=user_id)
        self.audit.record(
            action=AuditAction.CANCEL,
            entity_type="journal_entry",
            entity_id=entry.id,
            entity_label=entry.entry_no,
            remarks=f"Reversed by {reversal.entry_no}: {reason}",
        )
        return reversal

    # ------------------------------------------------------------ fiscal year
    def ensure_period(self, entry_date: date) -> tuple[FiscalPeriod | None, FiscalYear | None]:
        fiscal_year = self.db.execute(
            select(FiscalYear).where(
                FiscalYear.company_id == self.company_id,
                FiscalYear.start_date <= entry_date,
                FiscalYear.end_date >= entry_date,
                FiscalYear.is_closed.is_(False),
            )
        ).scalars().first()
        if fiscal_year is None:
            return None, None
        period = self.db.execute(
            select(FiscalPeriod).where(
                FiscalPeriod.fiscal_year_id == fiscal_year.id,
                FiscalPeriod.start_date <= entry_date,
                FiscalPeriod.end_date >= entry_date,
            )
        ).scalars().first()
        return period, fiscal_year

    # --------------------------------------------------------- sub-ledgers
    def post_customer_document(
        self,
        *,
        customer_id: uuid.UUID,
        document_type: str,
        document_id: uuid.UUID,
        document_no: str,
        document_date: date,
        amount: Decimal,
        is_debit: bool = True,
        due_date: date | None = None,
        currency_code: str | None = None,
        exchange_rate: Decimal = Decimal("1"),
        journal_entry_line_id: uuid.UUID | None = None,
        remarks: str | None = None,
    ) -> CustomerLedgerEntry:
        balance = self._customer_balance(customer_id)
        signed = (amount if is_debit else -amount)
        debit = money(amount) if is_debit else Decimal("0.00")
        credit = Decimal("0.00") if is_debit else money(amount)
        entry = CustomerLedgerEntry(
            company_id=self.company_id,
            customer_id=customer_id,
            document_type=document_type,
            document_id=document_id,
            document_no=document_no,
            document_date=document_date,
            due_date=due_date,
            debit=debit,
            credit=credit,
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            balance=money(balance + signed),
            is_open=True,
            journal_entry_line_id=journal_entry_line_id,
            remarks=remarks,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def post_supplier_document(
        self,
        *,
        supplier_id: uuid.UUID,
        document_type: str,
        document_id: uuid.UUID,
        document_no: str,
        document_date: date,
        amount: Decimal,
        is_credit: bool = True,
        due_date: date | None = None,
        currency_code: str | None = None,
        exchange_rate: Decimal = Decimal("1"),
        journal_entry_line_id: uuid.UUID | None = None,
        remarks: str | None = None,
    ) -> SupplierLedgerEntry:
        balance = self._supplier_balance(supplier_id)
        signed = (amount if is_credit else -amount)
        debit = Decimal("0.00") if is_credit else money(amount)
        credit = money(amount) if is_credit else Decimal("0.00")
        entry = SupplierLedgerEntry(
            company_id=self.company_id,
            supplier_id=supplier_id,
            document_type=document_type,
            document_id=document_id,
            document_no=document_no,
            document_date=document_date,
            due_date=due_date,
            debit=debit,
            credit=credit,
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            balance=money(balance + signed),
            is_open=True,
            journal_entry_line_id=journal_entry_line_id,
            remarks=remarks,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _customer_balance(self, customer_id: uuid.UUID) -> Decimal:
        value = self.db.execute(
            select(func.coalesce(func.sum(CustomerLedgerEntry.debit - CustomerLedgerEntry.credit), 0)).where(
                CustomerLedgerEntry.company_id == self.company_id,
                CustomerLedgerEntry.customer_id == customer_id,
            )
        ).scalar_one()
        return money(value)

    def _supplier_balance(self, supplier_id: uuid.UUID) -> Decimal:
        value = self.db.execute(
            select(func.coalesce(func.sum(SupplierLedgerEntry.credit - SupplierLedgerEntry.debit), 0)).where(
                SupplierLedgerEntry.company_id == self.company_id,
                SupplierLedgerEntry.supplier_id == supplier_id,
            )
        ).scalar_one()
        return money(value)

    def customer_balance(self, customer_id: uuid.UUID) -> Decimal:
        return self._customer_balance(customer_id)

    def supplier_balance(self, supplier_id: uuid.UUID) -> Decimal:
        return self._supplier_balance(supplier_id)

    # -------------------------------------------------------- settlement
    def allocate_payment(
        self,
        *,
        party_type: str,
        party_id: uuid.UUID,
        settlement_document_type: str,
        settlement_document_id: uuid.UUID,
        allocations: Iterable[dict[str, Any]],
        user_id: uuid.UUID | None = None,
    ) -> Decimal:
        """Apply a payment to target documents and mark fully settled ones."""
        total = Decimal("0")
        for allocation in allocations:
            target_type = allocation["document_type"]
            target_id = allocation["document_id"]
            amount = money(allocation["amount"])
            if amount <= 0:
                continue
            discount = money(allocation.get("discount_amount", 0))
            write_off = money(allocation.get("write_off_amount", 0))

            if party_type == PartyType.CUSTOMER.value:
                ledger = self.db.execute(
                    select(CustomerLedgerEntry).where(
                        CustomerLedgerEntry.company_id == self.company_id,
                        CustomerLedgerEntry.customer_id == party_id,
                        CustomerLedgerEntry.document_type == target_type,
                        CustomerLedgerEntry.document_id == target_id,
                    )
                ).scalars().first()
            else:
                ledger = self.db.execute(
                    select(SupplierLedgerEntry).where(
                        SupplierLedgerEntry.company_id == self.company_id,
                        SupplierLedgerEntry.supplier_id == party_id,
                        SupplierLedgerEntry.document_type == target_type,
                        SupplierLedgerEntry.document_id == target_id,
                    )
                ).scalars().first()
            if ledger is None:
                raise NotFoundError("Document to settle was not found in the sub-ledger", document=str(target_id))

            outstanding = (
                money(ledger.balance) if party_type == PartyType.CUSTOMER.value else money(-ledger.balance)
            )
            if amount + discount + write_off > outstanding + Decimal("0.01"):
                raise BusinessRuleError(
                    "Settlement exceeds the outstanding balance of the document",
                    document_no=ledger.document_no,
                    outstanding=str(outstanding),
                    attempted=str(amount + discount + write_off),
                )

            settled = amount + discount + write_off
            if party_type == PartyType.CUSTOMER.value:
                ledger.balance = money(ledger.balance - settled)
            else:
                ledger.balance = money(ledger.balance + settled)
            ledger.is_open = abs(ledger.balance) > Decimal("0.01")

            self.db.add(
                LedgerDocumentLink(
                    company_id=self.company_id,
                    party_type=party_type,
                    party_id=party_id,
                    settlement_document_type=settlement_document_type,
                    settlement_document_id=settlement_document_id,
                    target_document_type=target_type,
                    target_document_id=target_id,
                    amount=amount,
                    settled_at=datetime.now(UTC),
                    created_by_id=user_id,
                )
            )
            total += settled
        self.db.flush()
        return money(total)

    def refresh_payment_status(self, document: Any) -> None:
        """Recompute ``payment_status`` / ``is_fully_paid`` on a document."""
        total = money(getattr(document, "total_amount", 0))
        paid = money(getattr(document, "paid_amount", 0))
        balance = money(total - paid)
        document.balance_amount = balance
        if paid <= 0:
            document.payment_status = "unpaid"
        elif balance > Decimal("0.01"):
            document.payment_status = "partially_paid"
        elif balance < Decimal("-0.01"):
            document.payment_status = "overpaid"
        else:
            document.payment_status = "paid"
        if hasattr(document, "is_fully_paid"):
            document.is_fully_paid = document.payment_status == "paid"
        self.db.flush()

    # ------------------------------------------------------------- reporting
    def account_balance(
        self,
        account_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        branch_id: uuid.UUID | None = None,
        cost_center_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        party_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Return ``(debit_total, credit_total)`` for an account over a range."""
        stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                JournalEntryLine.company_id == self.company_id,
                JournalEntryLine.account_id == account_id,
                JournalEntry.status == DocumentStatus.POSTED.value,
                JournalEntry.deleted_at.is_(None),
            )
        )
        if date_from:
            stmt = stmt.where(JournalEntry.entry_date >= date_from)
        if date_to:
            stmt = stmt.where(JournalEntry.entry_date <= date_to)
        if branch_id:
            stmt = stmt.where(JournalEntryLine.branch_id == branch_id)
        if cost_center_id:
            stmt = stmt.where(JournalEntryLine.cost_center_id == cost_center_id)
        if project_id:
            stmt = stmt.where(JournalEntryLine.project_id == project_id)
        if party_id:
            stmt = stmt.where(JournalEntryLine.party_id == party_id)
        debit, credit = self.db.execute(stmt).one()
        return money(debit), money(credit)

    def account_balance_map(self) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        """All account balances in one query (used by trial balance / P&L)."""
        rows = self.db.execute(
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                JournalEntryLine.company_id == self.company_id,
                JournalEntry.status == DocumentStatus.POSTED.value,
                JournalEntry.deleted_at.is_(None),
            )
            .group_by(JournalEntryLine.account_id)
        ).all()
        return {row[0]: (money(row[1]), money(row[2])) for row in rows}


#: Fallback chart-of-accounts codes used when no posting rule is configured.
COMPANY_DEFAULT_ACCOUNTS: dict[str, str] = {
    "ar_account": "1210",
    "ap_account": "2110",
    "cash_account": "1110",
    "bank_account": "1120",
    "inventory_account": "1310",
    "cogs_account": "5110",
    "sales_revenue_account": "4110",
    "sales_discount_account": "4120",
    "purchase_expense_account": "5130",
    "purchase_discount_account": "5140",
    "tax_payable_account": "2210",
    "tax_receivable_account": "1410",
    "withholding_tax_account": "2220",
    "grni_account": "2130",
    "fx_gain_account": "4210",
    "fx_loss_account": "5210",
    "rounding_account": "4220",
    "retained_earnings_account": "3110",
    "inventory_adjustment_account": "5160",
    "scrap_account": "5170",
    "wip_account": "1320",
    "manufacturing_overhead_account": "5180",
    "salary_expense_account": "6110",
    "salary_payable_account": "2230",
    "employee_advance_account": "1420",
    "payroll_tax_account": "2240",
    "social_insurance_account": "2250",
    "depreciation_expense_account": "6120",
    "accumulated_depreciation_account": "1330",
    "asset_disposal_gain_account": "4230",
    "asset_disposal_loss_account": "5220",
    "expense_claim_account": "6130",
    "vat_input_account": "1410",
    "vat_output_account": "2210",
    "advance_from_customer_account": "2140",
    "prepaid_account": "1430",
    "suspense_account": "9999",
}

ACCOUNT_TYPE_BY_DEFAULT: dict[str, AccountType] = {
    "ar_account": AccountType.ASSET,
    "ap_account": AccountType.LIABILITY,
    "inventory_account": AccountType.ASSET,
    "cogs_account": AccountType.EXPENSE,
    "sales_revenue_account": AccountType.REVENUE,
    "cash_account": AccountType.ASSET,
    "bank_account": AccountType.ASSET,
}

NORMAL_BALANCE_FOR_TYPE: dict[str, str] = {
    AccountType.ASSET.value: NormalBalance.DEBIT.value,
    AccountType.EXPENSE.value: NormalBalance.DEBIT.value,
    AccountType.LIABILITY.value: NormalBalance.CREDIT.value,
    AccountType.EQUITY.value: NormalBalance.CREDIT.value,
    AccountType.REVENUE.value: NormalBalance.CREDIT.value,
}

CASH_FLOW_BY_DEFAULT: dict[str, str] = {
    "cash_account": CashFlowCategory.OPERATING.value,
    "bank_account": CashFlowCategory.OPERATING.value,
}


def validate_balanced(lines: Sequence[EntryLine]) -> None:
    """Utility used by callers building lines manually."""
    debit = money(sum(line.debit or 0 for line in lines))
    credit = money(sum(line.credit or 0 for line in lines))
    if debit != credit:
        raise ValidationFailure("Journal lines are not balanced", total_debit=str(debit), total_credit=str(credit))
