"""Expenses: categories, expense documents, employee claims, advances and budgets."""

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
from app.models.expenses import Budget, Expense, ExpenseAdvance, ExpenseCategory, ExpenseClaim
from app.services.expense_service import (
    BudgetService,
    ExpenseAdvanceService,
    ExpenseClaimService,
    ExpenseService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Categories
#
# The CRUD router below owns /{name}-categories (list, detail, create, update, delete).
# The previous hand written /categories endpoints duplicated it and collided with the
# other module that also served /categories, so they were removed in favour of one
# unambiguous collection per module.
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="expense-categories",
            model=ExpenseCategory,
            module="expenses",
            entity="expense_category",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(ExpenseCategory, unique=[("code", "Category code")]),
        ),
        tags=["expenses"],
    ),
    prefix="/expense-categories",
)

# --------------------------------------------------------------------------- #
# Expense documents
# --------------------------------------------------------------------------- #
expenses_router = build_document_router(
    DocumentSpec(
        name="expenses",
        service=ExpenseService,
        label="expenses",
        tag="expenses",
        party_field="supplier_id",
        search_fields=("document_no", "reference", "supplier_invoice_no"),
    )
)


@expenses_router.post("/{document_id}/pay", summary="Pay an approved expense")
def pay_expense(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("expenses.expense.edit")
    service = ExpenseService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    payment = service.pay(document_id, payload or None)
    db.flush()
    return serialise(payment)


router.include_router(expenses_router, prefix="/expenses")


@router.get("/expenses/summary", summary="Expenses grouped by category for a period")
def expense_summary(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("expenses.expense.view")
    today = date.today()
    start = date_from or today.replace(month=1, day=1)
    end = date_to or today
    rows = db.execute(
        select(
            Expense.category_id,
            func.count(Expense.id),
            func.coalesce(func.sum(Expense.total_amount), 0),
            func.coalesce(func.sum(Expense.paid_amount), 0),
        )
        .where(
            Expense.company_id == current.company_id,
            Expense.deleted_at.is_(None),
            Expense.document_date >= start,
            Expense.document_date <= end,
        )
        .group_by(Expense.category_id)
    ).all()
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "items": [
            {
                "category_id": str(row[0]) if row[0] else None,
                "count": int(row[1]),
                "amount": str(row[2]),
                "paid": str(row[3]),
                "outstanding": str(Decimal(row[2]) - Decimal(row[3])),
            }
            for row in rows
        ],
    }


# --------------------------------------------------------------------------- #
# Employee claims
# --------------------------------------------------------------------------- #
claims_router = build_document_router(
    DocumentSpec(
        name="expense-claims",
        service=ExpenseClaimService,
        label="expense claims",
        tag="expenses",
        date_field="claim_date",
        party_field="employee_id",
        search_fields=("claim_no", "purpose"),
    )
)


@claims_router.post("/{document_id}/pay", summary="Reimburse an approved claim")
def pay_claim(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("expenses.expense_claim.edit")
    payment = ExpenseClaimService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    ).pay(document_id, payload or None)
    db.flush()
    return serialise(payment)


@claims_router.get("/{document_id}/expenses", summary="Expenses attached to a claim")
def claim_expenses(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.expense_claim.view")
    claim = db.get(ExpenseClaim, document_id)
    if claim is None or claim.company_id != current.company_id:
        raise NotFoundError("Expense claim not found", id=str(document_id))
    rows = db.execute(
        select(Expense).where(
            Expense.company_id == current.company_id, Expense.claim_id == claim.id
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


router.include_router(claims_router, prefix="/expense-claims")
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="expense-claims",
            model=ExpenseClaim,
            module="expenses",
            entity="expense_claim",
            search_fields=["claim_no", "purpose"],
            default_sort="claim_date",
            filters={"employee_id": "employee_id", "status": "status"},
            soft_delete=False,
        ),
        tags=["expenses"],
    ),
    prefix="/expense-claim-register",
)

# --------------------------------------------------------------------------- #
# Advances
# --------------------------------------------------------------------------- #
@router.get("/advances", summary="Employee advances")
def list_advances(
    db: DB,
    current: CurrentUserDep,
    employee_id: uuid.UUID | None = None,
    outstanding_only: bool = False,
) -> dict[str, Any]:
    current.require("expenses.expense_advance.view")
    service = ExpenseAdvanceService(db, current.company_id)
    if outstanding_only or employee_id:
        rows = service.outstanding(employee_id=employee_id)
        if not outstanding_only:
            return {"items": rows, "total": len(rows)}
        return {"items": [row for row in rows if Decimal(row.get("balance_amount", 0)) > 0], "total": len(rows)}
    rows = db.execute(
        select(ExpenseAdvance)
        .where(ExpenseAdvance.company_id == current.company_id, ExpenseAdvance.deleted_at.is_(None))
        .order_by(ExpenseAdvance.advance_date.desc())
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/advances", status_code=201, summary="Issue an advance")
def create_advance(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.expense_advance.create")
    advance = ExpenseAdvanceService(db, current.company_id, user_id=current.id).create(payload)
    return serialise(advance)


@router.post("/advances/{advance_id}/approve-pay", summary="Approve and disburse an advance")
def approve_advance(
    advance_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("expenses.expense_advance.approve")
    service = ExpenseAdvanceService(db, current.company_id, user_id=current.id)
    advance = service.approve_and_pay(advance_id, payload or None)
    db.flush()
    return serialise(advance)


@router.post("/advances/{advance_id}/settle", summary="Settle an advance against a claim")
def settle_advance(advance_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.expense_advance.edit")
    service = ExpenseAdvanceService(db, current.company_id, user_id=current.id)
    advance = service.settle(
        advance_id,
        amount=Decimal(str(payload.get("amount", 0))),
        notes=payload.get("notes"),
    )
    db.flush()
    return serialise(advance)


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #
@router.get("/budgets", summary="Budgets with consumption")
def list_budgets(
    db: DB, current: CurrentUserDep, project_id: uuid.UUID | None = None, status_filter: str | None = Query(None, alias="status")
) -> dict[str, Any]:
    current.require("expenses.budget.view")
    stmt = select(Budget).where(Budget.company_id == current.company_id, Budget.deleted_at.is_(None))
    if project_id:
        stmt = stmt.where(Budget.project_id == project_id)
    if status_filter:
        stmt = stmt.where(Budget.status == status_filter)
    rows = db.execute(stmt.order_by(Budget.code)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/budgets", status_code=201, summary="Create a budget")
def create_budget(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.budget.create")
    budget = BudgetService(db, current.company_id, user_id=current.id).create(payload)
    return serialise(budget)


@router.get("/budgets/{budget_id}/report", summary="Budget vs actual")
def budget_report(budget_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.budget.view")
    return BudgetService(db, current.company_id).report(budget_id)


@router.post("/budgets/{budget_id}/commit", summary="Commit an amount against a budget line")
def commit_budget(budget_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("expenses.budget.edit")
    service = BudgetService(db, current.company_id, user_id=current.id)
    budget = service.commit(
        budget_id,
        budget_line_id=uuid.UUID(str(payload.get("budget_line_id"))),
        amount=Decimal(str(payload.get("amount", 0))),
    )
    return serialise(budget)


@router.get("/budgets/availability", summary="Budget availability for a cost centre/project/account")
def budget_availability(
    db: DB,
    current: CurrentUserDep,
    project_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    amount: str = Query("0"),
) -> dict[str, Any]:
    current.require("expenses.budget.view")
    service = BudgetService(db, current.company_id)
    available = service.check_availability(
        project_id=project_id, account_id=account_id, amount=Decimal(amount)
    )
    return {"available": available if isinstance(available, (bool, dict)) else str(available)}


# --------------------------------------------------------------------------- #
# Assistant endpoints
# --------------------------------------------------------------------------- #
@router.get("/my-expenses", summary="Expenses of the signed-in user (employee self service)")
def my_expenses(db: DB, current: CurrentUserDep, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    current.require("expenses.expense.view")
    rows = db.execute(
        select(Expense)
        .where(
            Expense.company_id == current.company_id,
            Expense.employee_id == current.user.employee_id,
            Expense.deleted_at.is_(None),
        )
        .order_by(Expense.document_date.desc())
        .limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = ValidationFailure

__all__ = ["router"]
