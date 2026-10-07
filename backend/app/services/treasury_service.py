"""Cash, bank, payments, receipts, transfers, cheques and reconciliation."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    BankReconciliationStatus,
    DocumentStatus,
    MovementType,
    PartyType,
    PaymentDirection,
    PaymentMethod,
    PaymentStatus,
)
from app.core.coercion import as_uuid
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.accounting import CustomerLedgerEntry, SupplierLedgerEntry
from app.models.masterdata import Customer, Supplier
from app.models.platform import Company
from app.models.treasury import (
    BankAccount,
    BankReconciliation,
    BankReconciliationLine,
    CashAccount,
    CashFlowSnapshot,
    Cheque,
    CurrencyRevaluation,
    Payment,
    PaymentAllocation,
    TreasuryTransfer,
)
from app.services.document_service import BaseDocumentService
from app.services.inventory_service import money


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


class TreasuryService(BaseDocumentService):
    """Payments / receipts with allocation, plus cash & bank account upkeep."""

    document_type = "payment"
    model = Payment
    line_model = None
    permission_module = "treasury"
    permission_entity = "payment"
    requires_lines = False

    # ------------------------------------------------------------------ setup
    def company(self) -> Company:
        company = self.db.get(Company, self.company_id)
        if company is None:
            raise NotFoundError("Company not found")
        return company

    def get_cash_account(self, cash_account_id: uuid.UUID | None) -> CashAccount | None:
        if not cash_account_id:
            return None
        account = self.db.execute(
            select(CashAccount).where(CashAccount.company_id == self.company_id, CashAccount.id == cash_account_id)
        ).scalars().first()
        if account is None:
            raise NotFoundError("Cash account not found")
        return account

    def get_bank_account(self, bank_account_id: uuid.UUID | None) -> BankAccount | None:
        if not bank_account_id:
            return None
        account = self.db.execute(
            select(BankAccount).where(BankAccount.company_id == self.company_id, BankAccount.id == bank_account_id)
        ).scalars().first()
        if account is None:
            raise NotFoundError("Bank account not found")
        return account

    # ---------------------------------------------------------------- capture
    def create(self, payload: dict[str, Any]) -> Payment:
        direction = str(payload.get("direction", PaymentDirection.INBOUND.value))
        if direction not in PaymentDirection.values():
            raise ValidationFailure("direction must be 'inbound' (receipt) or 'outbound' (payment)")
        party_type = str(payload.get("party_type", PartyType.CUSTOMER.value))
        party_id = as_uuid(payload.get("party_id"))
        party_name = payload.get("party_name")
        if party_id:
            party_id = uuid.UUID(str(party_id))
            if party_type == PartyType.CUSTOMER.value:
                customer = self.db.get(Customer, party_id)
                party_name = party_name or (customer.name if customer else None)
            elif party_type == PartyType.SUPPLIER.value:
                supplier = self.db.get(Supplier, party_id)
                party_name = party_name or (supplier.name if supplier else None)

        amount = money(payload.get("amount"))
        if amount <= 0:
            raise ValidationFailure("The payment amount must be greater than zero")

        cash_account = self.get_cash_account(as_uuid(payload.get("cash_account_id")))
        bank_account = self.get_bank_account(as_uuid(payload.get("bank_account_id")))
        if cash_account is None and bank_account is None and not as_uuid(payload.get("payment_account_id")):
            raise ValidationFailure("Select a cash account, bank account or GL payment account")

        document_date = payload.get("document_date") or date.today()
        currency_code = payload.get("currency_code") or (
            cash_account.currency_code if cash_account else bank_account.currency_code if bank_account else None
        )
        exchange_rate = _to_decimal(payload.get("exchange_rate") or 1) or Decimal("1")
        payment = Payment(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            direction=direction,
            payment_method=str(payload.get("payment_method", PaymentMethod.CASH.value)),
            party_type=party_type,
            party_id=party_id,
            party_name=party_name,
            cash_account_id=cash_account.id if cash_account else None,
            bank_account_id=bank_account.id if bank_account else None,
            payment_account_id=as_uuid(payload.get("payment_account_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            project_id=as_uuid(payload.get("project_id")),
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            amount=amount,
            amount_base=money(amount * exchange_rate),
            unallocated_amount=amount,
            withholding_tax_id=as_uuid(payload.get("withholding_tax_id")),
            withholding_amount=money(payload.get("withholding_amount")),
            reference=payload.get("reference"),
            description=payload.get("description"),
            cheque_number=payload.get("cheque_number"),
            cheque_date=payload.get("cheque_date"),
            card_reference=payload.get("card_reference"),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(payment)
        self.db.flush()

        allocations = payload.get("allocations") or []
        if allocations:
            self.allocate(payment, allocations)
        self.db.flush()
        self.audit.log_create(payment, entity_type="payment", label=payment.document_no)
        return payment

    def allocate(self, payment: Payment, allocations: Sequence[dict[str, Any]]) -> Decimal:
        total = Decimal("0")
        for allocation in allocations:
            amount = money(allocation.get("amount", 0))
            if amount <= 0:
                continue
            allocation_row = PaymentAllocation(
                company_id=self.company_id,
                payment_id=payment.id,
                target_document_type=str(allocation["document_type"]),
                target_document_id=uuid.UUID(str(allocation["document_id"])),
                target_document_no=allocation.get("document_no"),
                amount=amount,
                discount_amount=money(allocation.get("discount_amount")),
                write_off_amount=money(allocation.get("write_off_amount")),
            )
            self.db.add(allocation_row)
            total += money(allocation_row.amount + allocation_row.discount_amount + allocation_row.write_off_amount)
        payment.allocated_amount = money(total)
        payment.unallocated_amount = money(Decimal(payment.amount) - total)
        if payment.unallocated_amount < Decimal("-0.01"):
            raise BusinessRuleError(
                "Allocated amount exceeds the payment amount",
                allocated=str(total),
                amount=str(payment.amount),
            )

        # Update the target documents and the sub-ledgers.
        for allocation_row in payment.allocations:
            self._apply_allocation(payment, allocation_row)
        self.db.flush()
        return total

    def _apply_allocation(self, payment: Payment, allocation: PaymentAllocation) -> None:
        from app.models.purchasing import PurchaseInvoice
        from app.models.sales import CreditNote, SalesInvoice

        settled = money(allocation.amount + allocation.discount_amount + allocation.write_off_amount)
        target = None
        if allocation.target_document_type in {"sales_invoice", "pos_invoice"}:
            target = self.db.get(SalesInvoice, allocation.target_document_id)
        elif allocation.target_document_type == "credit_note":
            target = self.db.get(CreditNote, allocation.target_document_id)
        elif allocation.target_document_type == "purchase_invoice":
            target = self.db.get(PurchaseInvoice, allocation.target_document_id)

        if target is None:
            raise NotFoundError("The document being settled was not found")
        if target.status not in {DocumentStatus.POSTED.value, DocumentStatus.PARTIALLY_FULFILLED.value}:
            raise BusinessRuleError("Only posted documents can be settled")

        if payment.direction == PaymentDirection.INBOUND.value:
            target.paid_amount = money(Decimal(target.paid_amount or 0) + settled)
        else:
            target.paid_amount = money(Decimal(target.paid_amount or 0) + settled)
        self.posting.refresh_payment_status(target)

        self.posting.allocate_payment(
            party_type=payment.party_type,
            party_id=payment.party_id,
            settlement_document_type=payment.document_no,
            settlement_document_id=payment.id,
            allocations=[
                {
                    "document_type": allocation.target_document_type,
                    "document_id": allocation.target_document_id,
                    "amount": allocation.amount,
                    "discount_amount": allocation.discount_amount,
                    "write_off_amount": allocation.write_off_amount,
                }
            ],
            user_id=self.user_id,
        )

    # -------------------------------------------------------------- posting
    def build_journal_lines(self, document: Payment, inventory_result: Any = None) -> list[EntryLine]:
        from app.services.posting_service import EntryLine

        if document.cash_account_id:
            cash_account = self.get_cash_account(document.cash_account_id)
            treasury_gl_account_id = cash_account.account_id
        elif document.bank_account_id:
            bank_account = self.get_bank_account(document.bank_account_id)
            treasury_gl_account_id = bank_account.account_id
        else:
            treasury_gl_account_id = document.payment_account_id

        if treasury_gl_account_id is None:
            raise BusinessRuleError("No treasury account is configured for this payment")

        amount = money(document.amount)
        is_receipt = document.direction == PaymentDirection.INBOUND.value
        lines: list[EntryLine] = []

        if is_receipt:
            lines.append(
                EntryLine(
                    account_id=treasury_gl_account_id,
                    debit=amount,
                    description=f"Receipt {document.document_no}",
                    party_type=document.party_type,
                    party_id=document.party_id,
                    branch_id=document.branch_id,
                    cost_center_id=document.cost_center_id,
                    currency_code=document.currency_code,
                    exchange_rate=Decimal(document.exchange_rate or 1),
                )
            )
            if document.party_type == PartyType.CUSTOMER.value:
                settlement = self.posting.resolve_account(
                    "ar", document_type=self.document_type, fallback_code="1210"
                )
            elif document.payment_account_id:
                settlement = self.posting.account_by_id(document.payment_account_id)
            else:
                settlement = self.posting.resolve_account(
                    "ar", document_type=self.document_type, fallback_code="1210"
                )
            lines.append(
                EntryLine(
                    account_id=settlement.id,
                    credit=amount,
                    description=f"Settlement {document.document_no}",
                    party_type=document.party_type,
                    party_id=document.party_id,
                    branch_id=document.branch_id,
                    currency_code=document.currency_code,
                    exchange_rate=Decimal(document.exchange_rate or 1),
                )
            )
        else:
            if document.party_type == PartyType.SUPPLIER.value:
                settlement = self.posting.resolve_account(
                    "ap", document_type=self.document_type, fallback_code="2110"
                )
            elif document.payment_account_id:
                settlement = self.posting.account_by_id(document.payment_account_id)
            else:
                settlement = self.posting.resolve_account(
                    "ap", document_type=self.document_type, fallback_code="2110"
                )
            lines.append(
                EntryLine(
                    account_id=settlement.id,
                    debit=amount,
                    description=f"Settlement {document.document_no}",
                    party_type=document.party_type,
                    party_id=document.party_id,
                    branch_id=document.branch_id,
                    currency_code=document.currency_code,
                    exchange_rate=Decimal(document.exchange_rate or 1),
                )
            )
            if money(document.withholding_amount) > 0:
                withholding = self.posting.resolve_account(
                    "withholding_tax", document_type=self.document_type, fallback_code="2220"
                )
                lines.append(
                    EntryLine(
                        account_id=withholding.id,
                        credit=money(document.withholding_amount),
                        description="Withholding tax",
                        party_type=PartyType.SUPPLIER.value,
                        party_id=document.party_id,
                        branch_id=document.branch_id,
                    )
                )
            net_cash = money(amount - money(document.withholding_amount))
            lines.append(
                EntryLine(
                    account_id=treasury_gl_account_id,
                    credit=net_cash,
                    description=f"Payment {document.document_no}",
                    branch_id=document.branch_id,
                )
            )
        return lines

    def after_post(self, document: Payment, inventory_result: Any = None, entry: Any = None) -> None:
        signed = Decimal(document.amount) if document.direction == PaymentDirection.INBOUND.value else -Decimal(document.amount)
        if document.cash_account_id:
            cash_account = self.get_cash_account(document.cash_account_id)
            cash_account.current_balance = money(Decimal(cash_account.current_balance or 0) + signed)
        if document.bank_account_id:
            bank_account = self.get_bank_account(document.bank_account_id)
            bank_account.current_balance = money(Decimal(bank_account.current_balance or 0) + signed)
        self._snapshot(document)
        self.db.flush()

    def _snapshot(self, payment: Payment) -> None:
        """Record a cash-flow snapshot for cash/bank (or GL) accounts."""
        if payment.cash_account_id:
            account_kind = "cash"
            balance = self.get_cash_account(payment.cash_account_id).current_balance
        elif payment.bank_account_id:
            account_kind = "bank"
            balance = self.get_bank_account(payment.bank_account_id).current_balance
        elif payment.payment_account_id:
            account_kind = "gl"
            debit, credit = self.posting.account_balance(payment.payment_account_id)
            balance = money(debit - credit)
        else:
            return
        snapshot = CashFlowSnapshot(
            company_id=self.company_id,
            snapshot_date=payment.document_date,
            account_kind=account_kind,
            cash_account_id=payment.cash_account_id,
            bank_account_id=payment.bank_account_id,
            inflow=money(payment.amount) if payment.direction == PaymentDirection.INBOUND.value else money(0),
            outflow=money(payment.amount) if payment.direction == PaymentDirection.OUTBOUND.value else money(0),
            closing_balance=money(balance),
        )
        self.db.add(snapshot)

    # ---------------------------------------------------------------- helpers
    def post(self, document: Any, *, allow_draft: bool = False) -> Any:  # type: ignore[override]
        return super().post(document, allow_draft=allow_draft)

    def outstanding_documents(self, *, party_type: str, party_id: uuid.UUID, limit: int = 100) -> list[dict[str, Any]]:
        """Open invoices/credit notes for a party (used by the settlement UI)."""
        results: list[dict[str, Any]] = []
        if party_type == PartyType.CUSTOMER.value:
            rows = self.db.execute(
                select(CustomerLedgerEntry)
                .where(
                    CustomerLedgerEntry.company_id == self.company_id,
                    CustomerLedgerEntry.customer_id == party_id,
                    CustomerLedgerEntry.is_open.is_(True),
                )
                .order_by(CustomerLedgerEntry.document_date)
                .limit(limit)
            ).scalars().all()
            for row in rows:
                results.append(
                    {
                        "document_type": row.document_type,
                        "document_id": row.document_id,
                        "document_no": row.document_no,
                        "document_date": row.document_date,
                        "due_date": row.due_date,
                        "total": str(row.debit or row.credit),
                        "outstanding": str(row.balance),
                    }
                )
        else:
            rows = self.db.execute(
                select(SupplierLedgerEntry)
                .where(
                    SupplierLedgerEntry.company_id == self.company_id,
                    SupplierLedgerEntry.supplier_id == party_id,
                    SupplierLedgerEntry.is_open.is_(True),
                )
                .order_by(SupplierLedgerEntry.document_date)
                .limit(limit)
            ).scalars().all()
            for row in rows:
                results.append(
                    {
                        "document_type": row.document_type,
                        "document_id": row.document_id,
                        "document_no": row.document_no,
                        "document_date": row.document_date,
                        "due_date": row.due_date,
                        "total": str(row.credit or row.debit),
                        "outstanding": str(-row.balance),
                    }
                )
        return results

    def ageing(self, *, party_type: str = PartyType.CUSTOMER.value, as_of: date | None = None) -> dict[str, Any]:
        """Ageing buckets 0-30 / 31-60 / 61-90 / 90+ for a party type."""
        as_of = as_of or date.today()
        buckets = {"current": Decimal("0"), "0_30": Decimal("0"), "31_60": Decimal("0"), "61_90": Decimal("0"), "over_90": Decimal("0")}
        rows: list[dict[str, Any]] = []
        if party_type == PartyType.CUSTOMER.value:
            ledger_rows = self.db.execute(
                select(CustomerLedgerEntry).where(
                    CustomerLedgerEntry.company_id == self.company_id,
                    CustomerLedgerEntry.is_open.is_(True),
                    CustomerLedgerEntry.document_date <= as_of,
                )
            ).scalars().all()
            for row in ledger_rows:
                due = row.due_date or row.document_date
                days = (as_of - due).days
                outstanding = money(row.balance)
                if outstanding <= 0:
                    continue
                bucket = "current" if days <= 0 else "0_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
                buckets[bucket] += outstanding
                rows.append(
                    {
                        "party_id": row.customer_id,
                        "document_no": row.document_no,
                        "document_date": row.document_date,
                        "due_date": due,
                        "days_overdue": max(days, 0),
                        "outstanding": str(outstanding),
                        "bucket": bucket,
                    }
                )
        else:
            ledger_rows = self.db.execute(
                select(SupplierLedgerEntry).where(
                    SupplierLedgerEntry.company_id == self.company_id,
                    SupplierLedgerEntry.is_open.is_(True),
                    SupplierLedgerEntry.document_date <= as_of,
                )
            ).scalars().all()
            for row in ledger_rows:
                due = row.due_date or row.document_date
                days = (as_of - due).days
                outstanding = money(-row.balance)
                if outstanding <= 0:
                    continue
                bucket = "current" if days <= 0 else "0_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
                buckets[bucket] += outstanding
                rows.append(
                    {
                        "party_id": row.supplier_id,
                        "document_no": row.document_no,
                        "document_date": row.document_date,
                        "due_date": due,
                        "days_overdue": max(days, 0),
                        "outstanding": str(outstanding),
                        "bucket": bucket,
                    }
                )
        return {
            "as_of": as_of.isoformat(),
            "party_type": party_type,
            "buckets": {key: str(money(value)) for key, value in buckets.items()},
            "total": str(money(sum(buckets.values(), Decimal("0")))),
            "documents": rows,
        }


class TreasuryTransferService(BaseDocumentService):
    document_type = "treasury_transfer"
    model = TreasuryTransfer
    line_model = None
    permission_module = "treasury"
    permission_entity = "treasury_transfer"
    requires_lines = False

    def create(self, payload: dict[str, Any]) -> TreasuryTransfer:
        amount = money(payload.get("amount"))
        if amount <= 0:
            raise ValidationFailure("The transfer amount must be greater than zero")
        from_account = as_uuid(payload.get("from_cash_account_id")) or as_uuid(payload.get("from_bank_account_id"))
        to_account = as_uuid(payload.get("to_cash_account_id")) or as_uuid(payload.get("to_bank_account_id"))
        if not from_account or not to_account:
            raise ValidationFailure("Both source and destination accounts are required")
        if from_account == to_account:
            raise ValidationFailure("Source and destination accounts must differ")
        transfer = TreasuryTransfer(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=payload.get("document_date") or date.today(),
            from_cash_account_id=as_uuid(payload.get("from_cash_account_id")),
            to_cash_account_id=as_uuid(payload.get("to_cash_account_id")),
            from_bank_account_id=as_uuid(payload.get("from_bank_account_id")),
            to_bank_account_id=as_uuid(payload.get("to_bank_account_id")),
            amount=amount,
            charges=money(payload.get("charges")),
            currency_code=payload.get("currency_code"),
            exchange_rate=_to_decimal(payload.get("exchange_rate") or 1) or Decimal("1"),
            reference=payload.get("reference"),
            description=payload.get("description"),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(transfer)
        self.db.flush()
        self.audit.log_create(transfer, entity_type="treasury_transfer", label=transfer.document_no)
        return transfer

    def _gl_account(self, *, cash_account_id: uuid.UUID | None, bank_account_id: uuid.UUID | None) -> uuid.UUID:
        if cash_account_id:
            account = self.db.get(CashAccount, cash_account_id)
            if account:
                return account.account_id
        if bank_account_id:
            account = self.db.get(BankAccount, bank_account_id)
            if account:
                return account.account_id
        raise NotFoundError("Treasury account not found")

    def build_journal_lines(self, document: TreasuryTransfer, inventory_result: Any = None) -> list[EntryLine]:
        from app.services.posting_service import EntryLine

        source_gl = self._gl_account(
            cash_account_id=document.from_cash_account_id, bank_account_id=document.from_bank_account_id
        )
        destination_gl = self._gl_account(
            cash_account_id=document.to_cash_account_id, bank_account_id=document.to_bank_account_id
        )
        amount = money(document.amount)
        lines = [
            EntryLine(
                account_id=destination_gl,
                debit=amount,
                description=f"Transfer in {document.document_no}",
                branch_id=None,
            ),
            EntryLine(
                account_id=source_gl,
                credit=amount,
                description=f"Transfer out {document.document_no}",
            ),
        ]
        if money(document.charges) > 0:
            charges_account = self.posting.resolve_account(
                "bank_charges", document_type=self.document_type, fallback_code="5210"
            )
            lines.append(
                EntryLine(account_id=charges_account.id, debit=money(document.charges), description="Transfer charges")
            )
            lines[0].debit = money(amount - money(document.charges))
        return lines

    def after_post(self, document: TreasuryTransfer, inventory_result: Any = None, entry: Any = None) -> None:
        amount = money(document.amount)
        if document.from_cash_account_id:
            account = self.db.get(CashAccount, document.from_cash_account_id)
            if account:
                account.current_balance = money(Decimal(account.current_balance or 0) - amount)
        if document.from_bank_account_id:
            account = self.db.get(BankAccount, document.from_bank_account_id)
            if account:
                account.current_balance = money(Decimal(account.current_balance or 0) - amount)
        if document.to_cash_account_id:
            account = self.db.get(CashAccount, document.to_cash_account_id)
            if account:
                account.current_balance = money(Decimal(account.current_balance or 0) + amount - money(document.charges))
        if document.to_bank_account_id:
            account = self.db.get(BankAccount, document.to_bank_account_id)
            if account:
                account.current_balance = money(Decimal(account.current_balance or 0) + amount - money(document.charges))
        self.db.flush()


class ChequeService(BaseDocumentService):
    document_type = "cheque"
    model = Cheque
    line_model = None
    permission_module = "treasury"
    permission_entity = "cheque"
    requires_lines = False

    def register(self, payload: dict[str, Any]) -> Cheque:
        cheque = Cheque(
            company_id=self.company_id,
            cheque_number=payload["cheque_number"],
            direction=str(payload.get("direction", PaymentDirection.INBOUND.value)),
            party_type=payload.get("party_type"),
            party_id=as_uuid(payload.get("party_id")),
            bank_name=payload.get("bank_name"),
            bank_account_id=as_uuid(payload.get("bank_account_id")),
            amount=money(payload.get("amount")),
            currency_code=payload.get("currency_code"),
            issue_date=payload.get("issue_date") or date.today(),
            due_date=payload.get("due_date") or date.today(),
            status=payload.get("status", "pending"),
            notes=payload.get("notes"),
        )
        self.db.add(cheque)
        self.db.flush()
        return cheque

    def set_status(
        self, cheque_id: uuid.UUID, *, status: str, bank_account_id: uuid.UUID | None = None, reason: str | None = None
    ) -> Cheque:
        cheque = self.db.execute(
            select(Cheque).where(Cheque.company_id == self.company_id, Cheque.id == cheque_id)
        ).scalars().first()
        if cheque is None:
            raise NotFoundError("Cheque not found")
        valid = {"pending", "deposited", "cleared", "bounced", "cancelled", "endorsed"}
        if status not in valid:
            raise ValidationFailure(f"Invalid cheque status, expected one of {sorted(valid)}")
        cheque.status = status
        if status == "deposited":
            cheque.deposited_at = date.today()
        if status == "cleared":
            cheque.cleared_at = date.today()
        if status == "bounced":
            cheque.bounced_reason = reason
        if bank_account_id:
            cheque.bank_account_id = bank_account_id
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, cheque, entity_type="cheque", remarks=f"status -> {status}")
        return cheque


class BankReconciliationService(BaseDocumentService):
    document_type = "bank_reconciliation"
    model = BankReconciliation
    line_model = BankReconciliationLine
    permission_module = "treasury"
    permission_entity = "bank_reconciliation"
    requires_lines = False

    def create(self, payload: dict[str, Any]) -> BankReconciliation:
        bank_account_id = uuid.UUID(str(payload["bank_account_id"]))
        bank_account = self.db.get(BankAccount, bank_account_id)
        if bank_account is None:
            raise NotFoundError("Bank account not found")
        period_start = payload.get("period_start")
        period_end = payload.get("period_end") or date.today()
        if period_start is None:
            period_start = period_end.replace(day=1)
        reconciliation = BankReconciliation(
            company_id=self.company_id,
            document_no=self.next_number(),
            bank_account_id=bank_account_id,
            statement_date=payload.get("statement_date") or period_end,
            period_start=period_start,
            period_end=period_end,
            opening_balance=money(payload.get("opening_balance") or 0),
            statement_balance=money(payload.get("statement_balance") or 0),
            closing_balance=money(bank_account.current_balance),
            status=BankReconciliationStatus.DRAFT.value,
            notes=payload.get("notes"),
        )
        self.db.add(reconciliation)
        self.db.flush()

        # Auto-match posted payments inside the period.
        payments = self.db.execute(
            select(Payment).where(
                Payment.company_id == self.company_id,
                Payment.bank_account_id == bank_account_id,
                Payment.status == DocumentStatus.POSTED.value,
                Payment.document_date >= period_start,
                Payment.document_date <= period_end,
            )
        ).scalars().all()
        for payment in payments:
            self.db.add(
                BankReconciliationLine(
                    company_id=self.company_id,
                    reconciliation_id=reconciliation.id,
                    payment_id=payment.id,
                    transaction_date=payment.document_date,
                    amount=money(payment.amount),
                    direction="credit" if payment.direction == PaymentDirection.INBOUND.value else "debit",
                    is_matched=True,
                    statement_reference=payment.reference,
                )
            )
        self.db.flush()
        self.recalculate(reconciliation)
        return reconciliation

    def recalculate(self, reconciliation: BankReconciliation) -> BankReconciliation:
        debit = money(
            sum(
                (Decimal(line.amount) for line in reconciliation.lines if line.direction == "debit"),
                Decimal("0"),
            )
        )
        credit = money(
            sum(
                (Decimal(line.amount) for line in reconciliation.lines if line.direction == "credit"),
                Decimal("0"),
            )
        )
        reconciliation.closing_balance = money(Decimal(reconciliation.opening_balance or 0) + credit - debit)
        reconciliation.difference = money(Decimal(reconciliation.statement_balance or 0) - reconciliation.closing_balance)
        self.db.flush()
        return reconciliation

    def add_manual_line(
        self,
        reconciliation: BankReconciliation,
        *,
        amount: Decimal,
        direction: str,
        statement_reference: str | None = None,
        transaction_date: date | None = None,
        is_outstanding: bool = False,
    ) -> BankReconciliationLine:
        line = BankReconciliationLine(
            company_id=self.company_id,
            reconciliation_id=reconciliation.id,
            transaction_date=transaction_date or reconciliation.period_end,
            amount=money(amount),
            direction=direction,
            statement_reference=statement_reference,
            is_outstanding=is_outstanding,
            is_matched=not is_outstanding,
        )
        self.db.add(line)
        self.db.flush()
        self.recalculate(reconciliation)
        return line

    def complete(self, reconciliation_id: uuid.UUID, *, notes: str | None = None) -> BankReconciliation:
        reconciliation = self.get_document(reconciliation_id)
        self.recalculate(reconciliation)
        if abs(money(reconciliation.difference)) > Decimal("0.01") and not notes:
            raise BusinessRuleError(
                "The reconciliation does not balance; provide a note explaining the difference",
                difference=str(money(reconciliation.difference)),
            )
        reconciliation.status = BankReconciliationStatus.COMPLETED.value
        reconciliation.reconciled_by_id = self.user_id
        reconciliation.reconciled_at = datetime.now(UTC)
        reconciliation.notes = notes or reconciliation.notes
        self.db.flush()
        # Mark the matched journal lines as reconciled so they cannot be unposted.
        from app.models.accounting import JournalEntry, JournalEntryLine

        payment_ids = [line.payment_id for line in reconciliation.lines if line.payment_id]
        if payment_ids:
            payments = self.db.execute(select(Payment).where(Payment.id.in_(payment_ids))).scalars().all()
            for payment in payments:
                if payment.journal_entry_id:
                    lines = self.db.execute(
                        select(JournalEntryLine).where(
                            JournalEntryLine.entry_id == payment.journal_entry_id,
                            JournalEntryLine.account_id.is_not(None),
                        )
                    ).scalars().all()
                    for line in lines:
                        line.reconciled = True
                        line.reconciliation_id = reconciliation.id
        self.audit.log_action(
            AuditAction.APPROVE, reconciliation, entity_type="bank_reconciliation", remarks="reconciliation completed"
        )
        self.db.flush()
        return reconciliation


class CurrencyRevaluationService(BaseDocumentService):
    document_type = "currency_revaluation"
    model = CurrencyRevaluation
    line_model = None
    permission_module = "treasury"
    permission_entity = "currency_revaluation"
    requires_lines = False

    def run(
        self,
        *,
        currency_code: str,
        revaluation_date: date,
        new_rate: Decimal,
        old_rate: Decimal | None = None,
    ) -> CurrencyRevaluation:
        """Revalue open foreign-currency receivables/payables for a currency."""
        if new_rate <= 0:
            raise ValidationFailure("The new exchange rate must be positive")
        from app.models.platform import Company

        company = self.db.get(Company, self.company_id)
        company_currency = company.base_currency_code if company else None
        if company_currency and currency_code == company_currency:
            raise ValidationFailure("Revaluation must target a foreign currency")

        # Find the latest rate before this run if not provided.
        if old_rate is None:
            from app.models.platform import ExchangeRate

            previous = self.db.execute(
                select(ExchangeRate)
                .where(
                    ExchangeRate.company_id == self.company_id,
                    ExchangeRate.currency_code == currency_code,
                    ExchangeRate.effective_from <= revaluation_date,
                )
                .order_by(ExchangeRate.effective_from.desc())
            ).scalars().first()
            old_rate = Decimal(previous.rate) if previous else Decimal("1")

        foreign_total = Decimal("0")
        receivables = self.db.execute(
            select(CustomerLedgerEntry).where(
                CustomerLedgerEntry.company_id == self.company_id,
                CustomerLedgerEntry.currency_code == currency_code,
                CustomerLedgerEntry.is_open.is_(True),
            )
        ).scalars().all()
        for row in receivables:
            foreign_total += money(row.balance)
        payables = self.db.execute(
            select(SupplierLedgerEntry).where(
                SupplierLedgerEntry.company_id == self.company_id,
                SupplierLedgerEntry.currency_code == currency_code,
                SupplierLedgerEntry.is_open.is_(True),
            )
        ).scalars().all()
        for row in payables:
            foreign_total -= money(row.balance)

        gain_loss = money(foreign_total * (Decimal(new_rate) - Decimal(old_rate)))
        revaluation = CurrencyRevaluation(
            company_id=self.company_id,
            document_no=self.next_number(),
            revaluation_date=revaluation_date,
            currency_code=currency_code,
            old_rate=Decimal(old_rate),
            new_rate=Decimal(new_rate),
            foreign_amount=foreign_total,
            gain_loss_amount=gain_loss,
            fx_rate_used_percent=Decimal("0"),
            status=DocumentStatus.DRAFT.value,
        )
        self.db.add(revaluation)
        self.db.flush()
        return revaluation

    def build_journal_lines(self, document: CurrencyRevaluation, inventory_result: Any = None) -> list[EntryLine]:
        from app.services.posting_service import EntryLine

        amount = money(document.gain_loss_amount)
        if amount == 0:
            return []
        receivable = self.posting.resolve_account("ar", document_type=self.document_type, fallback_code="1210")
        gain = self.posting.resolve_account("fx_gain", document_type=self.document_type, fallback_code="4210")
        loss = self.posting.resolve_account("fx_loss", document_type=self.document_type, fallback_code="5210")
        if amount > 0:
            return [
                EntryLine(account_id=receivable.id, debit=amount, description="FX gain on revaluation"),
                EntryLine(account_id=gain.id, credit=amount, description="FX gain on revaluation"),
            ]
        return [
            EntryLine(account_id=loss.id, debit=abs(amount), description="FX loss on revaluation"),
            EntryLine(account_id=receivable.id, credit=abs(amount), description="FX loss on revaluation"),
        ]
