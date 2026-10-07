"""Cash and banks: accounts, receipts, payments, transfers, cheques and reconciliation."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError, ValidationFailure
from app.models.treasury import (
    BankAccount,
    BankReconciliation,
    BankReconciliationLine,
    CashAccount,
    Cheque,
    Payment,
    PaymentAllocation,
    TreasuryTransfer,
)
from app.services.treasury_service import (
    BankReconciliationService,
    ChequeService,
    CurrencyRevaluationService,
    TreasuryService,
    TreasuryTransferService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="cash-accounts",
            model=CashAccount,
            module="treasury",
            entity="cash_account",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"branch_id": "branch_id", "is_active": "is_active", "currency_code": "currency_code"},
            create_handler=guarded_create(CashAccount, unique=[("code", "Cash account code")]),
        ),
        tags=["treasury"],
    ),
    prefix="/cash-accounts",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="bank-accounts",
            model=BankAccount,
            module="treasury",
            entity="bank_account",
            search_fields=["code", "name", "bank_name", "account_number", "iban"],
            label_field="name",
            filters={"branch_id": "branch_id", "is_active": "is_active", "currency_code": "currency_code"},
            create_handler=guarded_create(BankAccount, unique=[("code", "Bank account code")]),
        ),
        tags=["treasury"],
    ),
    prefix="/bank-accounts",
)


@router.get("/cash-position", summary="Cash and bank position with GL reconciliation")
def cash_position(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("treasury.cash_account.view")
    from app.models.accounting import Account, JournalEntry, JournalEntryLine

    cash_total = db.execute(
        select(func.coalesce(func.sum(CashAccount.current_balance), 0)).where(
            CashAccount.company_id == current.company_id, CashAccount.deleted_at.is_(None)
        )
    ).scalar_one()
    bank_total = db.execute(
        select(func.coalesce(func.sum(BankAccount.current_balance), 0)).where(
            BankAccount.company_id == current.company_id, BankAccount.deleted_at.is_(None)
        )
    ).scalar_one()
    gl_total = db.execute(
        select(func.coalesce(func.sum(JournalEntryLine.debit - JournalEntryLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .where(
            JournalEntryLine.company_id == current.company_id,
            JournalEntry.status == "posted",
            Account.is_cash_account.is_(True) | Account.is_bank_account.is_(True),
        )
    ).scalar_one()
    return {
        "cash_accounts": str(cash_total),
        "bank_accounts": str(bank_total),
        "total": str(Decimal(cash_total) + Decimal(bank_total)),
        "gl_balance": str(gl_total),
        "difference": str(Decimal(cash_total) + Decimal(bank_total) - Decimal(gl_total)),
        "as_of": date.today().isoformat(),
    }


# --------------------------------------------------------------------------- #
# Payments and receipts
# --------------------------------------------------------------------------- #
payments_router = build_document_router(
    DocumentSpec(
        name="payments",
        service=TreasuryService,
        label="payments",
        tag="treasury",
        party_field="party_id",
        search_fields=("document_no", "reference"),
    )
)


@payments_router.post("/{document_id}/allocate", summary="Allocate a payment to invoices")
def allocate_payment(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("treasury.payment.edit")
    service = TreasuryService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    payment = service.get_document(document_id)
    allocations = payload.get("allocations") or payload if isinstance(payload, list) else []
    if isinstance(payload, dict) and payload.get("allocations") is None:
        allocations = [payload] if payload.get("target_document_id") else []
    if not allocations:
        raise ValidationFailure("At least one allocation is required")
    allocated = service.allocate(payment, allocations)
    db.flush()
    return {"payment_id": str(payment.id), "allocated": str(allocated)}


@payments_router.get("/{document_id}/allocations", summary="Allocations of a payment")
def payment_allocations(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("treasury.payment.view")
    rows = db.execute(
        select(PaymentAllocation).where(
            PaymentAllocation.company_id == current.company_id, PaymentAllocation.payment_id == document_id
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


router.include_router(payments_router, prefix="/payments")


@router.get("/payments/outstanding", summary="Open invoices for a party (payment allocation screen)")
def outstanding_documents(
    db: DB,
    current: CurrentUserDep,
    party_type: str = Query("customer", pattern="^(customer|supplier)$"),
    party_id: uuid.UUID = Query(...),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("treasury.payment.view")
    service = TreasuryService(db, current.company_id, user_id=current.id)
    items = service.outstanding_documents(party_type=party_type, party_id=party_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/payments/ageing", summary="AR/AP ageing")
def payment_ageing(
    db: DB,
    current: CurrentUserDep,
    party_type: str = Query("customer", pattern="^(customer|supplier)$"),
    as_of: date | None = None,
) -> dict[str, Any]:
    current.require("treasury.payment.view")
    service = TreasuryService(db, current.company_id, user_id=current.id)
    return service.ageing(party_type=party_type, as_of=as_of or date.today())


# --------------------------------------------------------------------------- #
# Transfers
# --------------------------------------------------------------------------- #
router.include_router(
    build_document_router(
        DocumentSpec(name="transfers", service=TreasuryTransferService, label="treasury transfers", tag="treasury")
    ),
    prefix="/transfers",
)

# --------------------------------------------------------------------------- #
# Cheques
# --------------------------------------------------------------------------- #
@router.get("/cheques", summary="Cheques with due status")
def list_cheques(
    db: DB,
    current: CurrentUserDep,
    direction: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    due_before: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("treasury.cheque.view")
    stmt = select(Cheque).where(Cheque.company_id == current.company_id, Cheque.deleted_at.is_(None))
    if direction:
        stmt = stmt.where(Cheque.direction == direction)
    if status_filter:
        stmt = stmt.where(Cheque.status == status_filter)
    if due_before:
        stmt = stmt.where(Cheque.due_date <= due_before)
    rows = db.execute(stmt.order_by(Cheque.due_date.asc().nulls_last()).limit(limit)).scalars().all()
    today = date.today()
    items = []
    for row in rows:
        payload = serialise(row)
        payload["overdue"] = bool(row.due_date and row.status in {"pending", "deposited"} and row.due_date < today)
        items.append(payload)
    return {"items": items, "total": len(items)}


@router.post("/cheques", status_code=201, summary="Register a cheque")
def register_cheque(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("treasury.cheque.create")
    cheque = ChequeService(db, current.company_id, user_id=current.id).register(payload)
    db.flush()
    return serialise(cheque)


@router.post("/cheques/{cheque_id}/status", summary="Deposit, clear, bounce or cancel a cheque")
def cheque_status(
    cheque_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("treasury.cheque.edit")
    cheque = ChequeService(db, current.company_id, user_id=current.id).set_status(
        cheque_id,
        status=payload.get("status") or "cleared",
        bank_account_id=uuid.UUID(str(payload["bank_account_id"])) if payload.get("bank_account_id") else None,
        reason=payload.get("reason"),
    )
    db.flush()
    return serialise(cheque)


# --------------------------------------------------------------------------- #
# Bank reconciliation
# --------------------------------------------------------------------------- #
recon_router = build_document_router(
    DocumentSpec(
        name="bank-reconciliations",
        service=BankReconciliationService,
        label="bank reconciliations",
        tag="treasury",
        date_field="statement_date",
    )
)


@recon_router.post("/{document_id}/lines", summary="Add a statement line")
def add_statement_line(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("treasury.bank_reconciliation.edit")
    service = BankReconciliationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    reconciliation = service.get_document(document_id)
    line = service.add_manual_line(
        reconciliation,
        amount=Decimal(str(payload.get("amount", 0))),
        direction=payload.get("direction", "in"),
        statement_reference=payload.get("statement_reference"),
        transaction_date=date.fromisoformat(payload["transaction_date"]) if payload.get("transaction_date") else None,
        is_outstanding=bool(payload.get("is_outstanding", False)),
    )
    db.flush()
    return serialise(line)


@recon_router.post("/{document_id}/complete", summary="Complete the reconciliation")
def complete_reconciliation(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("treasury.bank_reconciliation.edit")
    from app.models.treasury import BankReconciliation as Model

    service = BankReconciliationService(db, current.company_id, user_id=current.id)
    reconciliation = db.get(Model, document_id)
    if reconciliation is None or reconciliation.company_id != current.company_id:
        raise NotFoundError("Bank reconciliation not found", id=str(document_id))
    result = service.complete(document_id, notes=payload.get("notes"))
    db.flush()
    return serialise(result)


@router.get("/bank-reconciliation/pending", summary="Statement lines waiting to be matched")
def pending_statement_lines(
    db: DB, current: CurrentUserDep, bank_account_id: uuid.UUID | None = None, limit: int = Query(200, ge=1, le=1000)
) -> dict[str, Any]:
    current.require("treasury.bank_reconciliation.view")
    stmt = select(BankReconciliationLine).where(
        BankReconciliationLine.company_id == current.company_id, BankReconciliationLine.is_matched.is_(False)
    )
    if bank_account_id:
        stmt = stmt.join(
            BankReconciliation, BankReconciliation.id == BankReconciliationLine.reconciliation_id
        ).where(BankReconciliation.bank_account_id == bank_account_id)
    rows = db.execute(
        stmt.order_by(BankReconciliationLine.transaction_date.desc()).limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


# --------------------------------------------------------------------------- #
# Currency revaluation
# --------------------------------------------------------------------------- #
@router.post("/currency-revaluation/run", status_code=201, summary="Revalue open foreign-currency balances")
def run_revaluation(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("treasury.currency_revaluation.create")
    service = CurrencyRevaluationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    target_date = date.fromisoformat(payload["revaluation_date"]) if payload.get("revaluation_date") else date.today()
    new_rates: dict[str, Any] = payload.get("rates") or {}
    if payload.get("currency_code"):
        new_rates.setdefault(payload["currency_code"], payload.get("new_rate"))
    if not new_rates:
        raise ValidationFailure("Provide 'rates' ({'EUR': '50.25'}) or currency_code + new_rate")
    documents = []
    for currency_code, new_rate in new_rates.items():
        if new_rate in (None, ""):
            continue
        documents.append(
            service.run(
                currency_code=str(currency_code).upper(),
                revaluation_date=target_date,
                new_rate=Decimal(str(new_rate)),
                old_rate=Decimal(str(payload["old_rate"])) if payload.get("old_rate") else None,
            )
        )
    db.flush()
    return {"items": [serialise(item) for item in documents], "total": len(documents)}


# --------------------------------------------------------------------------- #
# Registers
# --------------------------------------------------------------------------- #
@router.get("/registers/cash-book", summary="Cash book for one account")
def cash_book(
    db: DB,
    current: CurrentUserDep,
    account_id: uuid.UUID = Query(...),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("treasury.receipt.view")
    from app.services.report_service import ReportService

    today = date.today()
    result = ReportService(db, current.company_id).general_ledger(
        account_id=account_id,
        date_from=date_from or today.replace(month=1, day=1),
        date_to=date_to or today,
    )
    return result.to_dict()


@router.get("/registers/daily-collection", summary="Daily collections by method")
def daily_collection(
    db: DB,
    current: CurrentUserDep,
    on_date: date | None = None,
) -> dict[str, Any]:
    current.require("treasury.receipt.view")
    target = on_date or date.today()
    rows = db.execute(
        select(
            Payment.payment_method,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .where(
            Payment.company_id == current.company_id,
            Payment.direction == "inbound",
            func.date(Payment.document_date) == target,
        )
        .group_by(Payment.payment_method)
    ).all()
    return {
        "date": target.isoformat(),
        "items": [
            {"method": row[0] or "other", "count": int(row[1]), "amount": str(row[2])} for row in rows
        ],
        "total": str(sum(Decimal(row[2]) for row in rows)) if rows else "0",
    }


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = (TreasuryTransfer,)

__all__ = ["router"]
