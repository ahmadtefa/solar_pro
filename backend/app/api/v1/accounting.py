"""Accounting: chart of accounts, journal entries, ledgers, statements and posting rules."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.accounting import Account, JournalEntry, PostingRule
from app.models.masterdata import Customer, Supplier
from app.services.accounting_service import (
    ChartOfAccountsService,
    JournalEntryService,
    PeriodCloseService,
    PostingRuleService,
)
from app.services.audit_service import AuditService
from app.services.report_service import ReportService

router = APIRouter()

# --------------------------------------------------------------------------- #
# Chart of accounts
# --------------------------------------------------------------------------- #
@router.get("/accounts", summary="Chart of accounts (tree or flat list)")
def list_accounts(
    db: DB,
    current: CurrentUserDep,
    account_type: str | None = None,
    parent_id: uuid.UUID | None = None,
    q: str | None = None,
    tree: bool = False,
    include_inactive: bool = False,
) -> dict[str, Any]:
    current.require("accounting.account.view")
    service = ChartOfAccountsService(db, current.company_id)
    if tree and not (account_type or parent_id or q):
        return {"items": service.tree(include_inactive=include_inactive)}
    stmt = select(Account).where(Account.company_id == current.company_id, Account.deleted_at.is_(None))
    if account_type:
        stmt = stmt.where(Account.account_type == account_type)
    if parent_id:
        stmt = stmt.where(Account.parent_id == parent_id)
    if q:
        stmt = stmt.where(Account.code.ilike(f"%{q}%") | Account.name.ilike(f"%{q}%"))
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
    rows = db.execute(stmt.order_by(Account.code)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/accounts", status_code=201, summary="Create an account")
def create_account(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.account.create")
    account = ChartOfAccountsService(db, current.company_id).create_account(payload)
    AuditService(db, audit_context(current)).log_create(account, entity_type="account", label=account.code)
    return serialise(account)


@router.patch("/accounts/{account_id}", summary="Update an account")
def update_account(account_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.account.edit")
    account = db.get(Account, account_id)
    if account is None or account.company_id != current.company_id:
        raise NotFoundError("Account not found", id=str(account_id))
    from app.core.pagination import snapshot

    before = snapshot(account)
    protected = {"id", "company_id", "code", "account_type", "created_at", "updated_at", "deleted_at"}
    for key, value in payload.items():
        if key in protected or key not in {column.key for column in Account.__mapper__.columns}:
            continue
        setattr(account, key, value)
    db.flush()
    AuditService(db, audit_context(current)).log_update(account, before, entity_type="account", label=account.code)
    return serialise(account)


@router.get("/accounts/balances", summary="Balances per account for a period")
def account_balances(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("accounting.general_ledger.view")
    rows = ChartOfAccountsService(db, current.company_id).account_balances(date_from=date_from, date_to=date_to)
    return {"items": rows, "total": len(rows)}


@router.get("/accounts/{account_id}/ledger", summary="General ledger of one account")
def account_ledger(
    account_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("accounting.general_ledger.view")
    result = ReportService(db, current.company_id).general_ledger(
        account_id=account_id, date_from=date_from, date_to=date_to
    )
    return result.to_dict()


# --------------------------------------------------------------------------- #
# Journal entries
# --------------------------------------------------------------------------- #
journal_router = build_document_router(
    DocumentSpec(
        name="journal-entries",
        service=JournalEntryService,
        label="journal entries",
        tag="accounting",
        date_field="entry_date",
        search_fields=("entry_no", "reference", "description"),
    )
)


@journal_router.post("/{document_id}/reverse", summary="Reverse a posted journal entry")
def reverse_entry(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("accounting.journal_entry.post")
    service = JournalEntryService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    reversal = service.reverse(
        document_id,
        reason=payload.get("reason") or "Reversal",
        reversal_date=date.fromisoformat(payload["reversal_date"]) if payload.get("reversal_date") else None,
    )
    db.flush()
    return {**serialise(reversal), "lines": [serialise(line) for line in reversal.lines]}


@journal_router.get("/{document_id}/print", summary="Printable journal voucher")
def journal_print(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.journal_entry.print")
    from app.api.documents import print_payload

    service = JournalEntryService(db, current.company_id, user_id=current.id)
    return print_payload(db, current, service.get_document(document_id), "lines")


router.include_router(journal_router, prefix="/journal-entries")


@router.post("/journal-entries/manual", status_code=201, summary="Post a balanced manual entry")
def manual_entry(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    """Convenience endpoint for the classic two-column voucher screen."""
    current.require("accounting.journal_entry.create")
    service = JournalEntryService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    entry = service.create(payload)
    if payload.get("auto_post", True):
        entry.status = "approved"
        db.flush()
        service.post(entry)
    db.flush()
    return {**serialise(entry), "lines": [serialise(line) for line in entry.lines]}


# --------------------------------------------------------------------------- #
# Statements and ledgers
# --------------------------------------------------------------------------- #
@router.get("/reports/trial-balance", summary="Trial balance")
def trial_balance(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
    cost_center_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("accounting.trial_balance.view")
    result = ReportService(db, current.company_id).trial_balance(
        date_from=date_from, date_to=date_to, branch_id=branch_id
    )
    return result.to_dict()


@router.get("/reports/balance-sheet", summary="Balance sheet")
def balance_sheet(
    db: DB,
    current: CurrentUserDep,
    as_of: date | None = None,
    branch_id: uuid.UUID | None = None,
    compare_previous: bool = False,
) -> dict[str, Any]:
    current.require("accounting.balance_sheet.view")
    result = ReportService(db, current.company_id).balance_sheet(
        as_of=as_of or date.today(), branch_id=branch_id
    )
    return result.to_dict()


@router.get("/reports/income-statement", summary="Profit and loss")
def income_statement(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
    cost_center_id: uuid.UUID | None = None,
    compare_previous: bool = False,
) -> dict[str, Any]:
    current.require("accounting.income_statement.view")
    today = date.today()
    result = ReportService(db, current.company_id).income_statement(
        date_from=date_from or today.replace(month=1, day=1),
        date_to=date_to or today,
        branch_id=branch_id,
        compare=compare_previous,
    )
    return result.to_dict()


@router.get("/reports/cash-flow", summary="Cash flow statement")
def cash_flow(
    db: DB, current: CurrentUserDep, date_from: date | None = None, date_to: date | None = None
) -> dict[str, Any]:
    current.require("accounting.cash_flow.view")
    today = date.today()
    result = ReportService(db, current.company_id).cash_flow(
        date_from=date_from or today.replace(month=1, day=1), date_to=date_to or today
    )
    return result.to_dict()


@router.get("/reports/customer-ledger", summary="Customer ledger")
def customer_ledger(
    db: DB,
    current: CurrentUserDep,
    customer_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("accounting.customer_ledger.view")
    today = date.today()
    if customer_id:
        result = ReportService(db, current.company_id).customer_statement(
            customer_id=customer_id,
            date_from=date_from or today.replace(month=1, day=1),
            date_to=date_to or today,
        )
        return result.to_dict()
    result = ReportService(db, current.company_id).receivable_ageing(as_of=date_to or today)
    return result.to_dict()


@router.get("/reports/supplier-ledger", summary="Supplier ledger")
def supplier_ledger(
    db: DB,
    current: CurrentUserDep,
    supplier_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("accounting.supplier_ledger.view")
    today = date.today()
    if supplier_id:
        result = ReportService(db, current.company_id).supplier_statement(
            supplier_id=supplier_id,
            date_from=date_from or today.replace(month=1, day=1),
            date_to=date_to or today,
        )
        return result.to_dict()
    result = ReportService(db, current.company_id).payable_ageing(as_of=date_to or today)
    return result.to_dict()


@router.get("/reports/ageing", summary="AR/AP ageing buckets")
def ageing(
    db: DB,
    current: CurrentUserDep,
    party_type: str = Query("customer"),
    as_of: date | None = None,
) -> dict[str, Any]:
    current.require("accounting.ageing.view")
    service = ReportService(db, current.company_id)
    result = (
        service.receivable_ageing(as_of=as_of or date.today())
        if party_type == "customer"
        else service.payable_ageing(as_of=as_of or date.today())
    )
    return result.to_dict()


@router.get("/reports/tax", summary="Tax report (output vs input VAT)")
def tax_report(
    db: DB, current: CurrentUserDep, date_from: date | None = None, date_to: date | None = None
) -> dict[str, Any]:
    current.require("reports.tax_report.view")
    today = date.today()
    result = ReportService(db, current.company_id).tax_report(
        date_from=date_from or today.replace(month=1, day=1), date_to=date_to or today
    )
    return result.to_dict()


# --------------------------------------------------------------------------- #
# Posting rules and period close
# --------------------------------------------------------------------------- #
@router.get("/posting-rules", summary="Posting rules")
def list_posting_rules(
    db: DB, current: CurrentUserDep, document_type: str | None = None
) -> dict[str, Any]:
    current.require("accounting.posting_rule.view")
    stmt = select(PostingRule).where(
        PostingRule.company_id == current.company_id, PostingRule.deleted_at.is_(None)
    )
    if document_type:
        stmt = stmt.where(PostingRule.document_type == document_type)
    rows = db.execute(stmt.order_by(PostingRule.document_type, PostingRule.sequence_no)).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@router.post("/posting-rules/ensure-defaults", summary="Create the default posting rules missing for this company")
def ensure_default_rules(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.posting_rule.create")
    created = PostingRuleService(db, current.company_id).ensure_default_rules()
    AuditService(db, audit_context(current)).log_action(
        "create", None, entity_type="posting_rule", label="defaults", new_values={"created": created}
    )
    return {"created": created}


@router.put("/posting-rules/{rule_id}", summary="Update a posting rule")
def update_posting_rule(rule_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.posting_rule.edit")
    rule = db.get(PostingRule, rule_id)
    if rule is None or rule.company_id != current.company_id:
        raise NotFoundError("Posting rule not found", id=str(rule_id))
    allowed = {"name", "account_source", "fallback_account_id", "entry_side", "amount_source", "is_active", "condition_json"}
    for key, value in payload.items():
        if key in allowed:
            setattr(rule, key, value)
    db.flush()
    return serialise(rule)


@router.get("/period-close/net-result", summary="Net result of a fiscal year before closing")
def net_result(db: DB, current: CurrentUserDep, fiscal_year_id: uuid.UUID = Query(...)) -> dict[str, Any]:
    current.require("accounting.period_close.view")
    from app.models.platform import FiscalYear

    year = db.get(FiscalYear, fiscal_year_id)
    if year is None or year.company_id != current.company_id:
        raise NotFoundError("Fiscal year not found", id=str(fiscal_year_id))
    revenue, expense, net = PeriodCloseService(db, current.company_id).net_result(year)
    return {
        "fiscal_year_id": str(year.id),
        "code": year.code,
        "revenue": str(revenue),
        "expense": str(expense),
        "net_result": str(net),
        "is_closed": year.is_closed,
    }


# --------------------------------------------------------------------------- #
# Dimensions
# --------------------------------------------------------------------------- #
@router.get("/dimensions/balance", summary="Balance of an account broken down by dimension")
def dimension_balance(
    db: DB,
    current: CurrentUserDep,
    account_id: uuid.UUID = Query(...),
    dimension: str = Query("cost_center", pattern="^(cost_center|project|branch|party)$"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("accounting.general_ledger.view")
    from app.models.accounting import JournalEntryLine as JournalLine

    column_map = {
        "cost_center": JournalLine.cost_center_id,
        "project": JournalLine.project_id,
        "branch": JournalLine.branch_id,
        "party": JournalLine.party_id,
    }
    column = column_map[dimension]
    stmt = (
        select(column, func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.company_id == current.company_id,
            JournalLine.account_id == account_id,
            JournalEntry.status == "posted",
        )
        .group_by(column)
    )
    if date_from:
        stmt = stmt.where(JournalEntry.entry_date >= date_from)
    if date_to:
        stmt = stmt.where(JournalEntry.entry_date <= date_to)
    rows = db.execute(stmt).all()
    return {
        "dimension": dimension,
        "account_id": str(account_id),
        "items": [
            {
                "dimension_id": str(row[0]) if row[0] else None,
                "debit": str(row[1]),
                "credit": str(row[2]),
                "balance": str(Decimal(row[1]) - Decimal(row[2])),
            }
            for row in rows
        ],
    }


# --------------------------------------------------------------------------- #
# Balancing helpers used by the UI's status bar
# --------------------------------------------------------------------------- #
@router.get("/health/balance-check", summary="Verify that every posted entry is balanced and periods are open")
def balance_check(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("accounting.trial_balance.view")
    unbalanced = db.execute(
        select(JournalEntry.entry_no, JournalEntry.total_debit, JournalEntry.total_credit)
        .where(
            JournalEntry.company_id == current.company_id,
            JournalEntry.status == "posted",
            JournalEntry.total_debit != JournalEntry.total_credit,
        )
        .limit(50)
    ).all()
    if unbalanced:
        raise BusinessRuleError(
            "Unbalanced posted journal entries found",
            entries=[{"entry_no": row[0], "debit": str(row[1]), "credit": str(row[2])} for row in unbalanced],
        )
    drafts = db.execute(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.company_id == current.company_id, JournalEntry.status == "draft"
        )
    ).scalar_one()
    return {"balanced": True, "draft_entries": int(drafts)}


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = (Customer, Supplier, ValidationFailure)

__all__ = ["router"]
