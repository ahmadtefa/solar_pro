"""Expenses, employee claims, advances and budget control."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import DocumentStatus, PartyType, PaymentDirection, PaymentMethod
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.expenses import (
    Budget,
    BudgetLine,
    Expense,
    ExpenseAdvance,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseLine,
)
from app.models.masterdata import Supplier
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.posting_service import EntryLine, PostingService, money

ZERO = Decimal("0")


class ExpenseCategoryService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> ExpenseCategory:
        code = str(payload["code"]).strip().upper()
        if self.db.execute(
            select(ExpenseCategory).where(
                ExpenseCategory.company_id == self.company_id, ExpenseCategory.code == code
            )
        ).scalars().first():
            raise ConflictError(f"Expense category {code} already exists")
        category = ExpenseCategory(
            company_id=self.company_id,
            code=code,
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            parent_id=as_uuid(payload.get("parent_id")),
            expense_account_id=as_uuid(payload.get("expense_account_id")),
            payable_account_id=as_uuid(payload.get("payable_account_id")),
            default_tax_id=as_uuid(payload.get("default_tax_id")),
            requires_receipt=bool(payload.get("requires_receipt", True)),
            requires_cost_center=bool(payload.get("requires_cost_center", False)),
            requires_project=bool(payload.get("requires_project", False)),
            requires_approval=bool(payload.get("requires_approval", True)),
            approval_threshold=money(payload.get("approval_threshold")),
            budget_amount=money(payload.get("budget_amount")),
            description=payload.get("description"),
        )
        self.db.add(category)
        self.db.flush()
        self.audit.log_create(category, entity_type="expense_category", label=category.code)
        return category

    def list(self) -> list[ExpenseCategory]:
        return list(
            self.db.execute(
                select(ExpenseCategory)
                .where(ExpenseCategory.company_id == self.company_id)
                .order_by(ExpenseCategory.code)
            ).scalars().all()
        )


class ExpenseService(BaseDocumentService):
    """Vendor / petty cash expenses with tax recovery and approval."""

    document_type = "expense"
    model = Expense
    line_model = ExpenseLine
    line_relationship = "lines"
    permission_entity = "expense"
    permission_module = "expenses"
    requires_lines = True

    def create(self, payload: dict[str, Any]) -> Expense:
        category = None
        if payload.get("category_id"):
            category = self.db.get(ExpenseCategory, as_uuid(payload["category_id"]))
            if category is None:
                raise NotFoundError("Expense category not found")
        lines_input = payload.get("lines") or []
        if not lines_input:
            raise ValidationFailure("An expense requires at least one line")
        rows, totals = self.build_lines(lines_input, purchase=True)
        payee_type = str(payload.get("payee_type") or PartyType.SUPPLIER.value)
        payee_id = as_uuid(payload.get("payee_id"))
        supplier_id = as_uuid(payload.get("supplier_id"))
        employee_id = as_uuid(payload.get("employee_id"))
        if payee_id is None:
            payee_id = employee_id if payee_type == PartyType.EMPLOYEE.value else supplier_id
        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        expense = Expense(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            due_date=payload.get("due_date") or document_date,
            category_id=category.id if category else as_uuid(payload.get("category_id")),
            expense_type=payload.get("expense_type", "operating"),
            payee_type=payee_type,
            payee_id=payee_id,
            payee_name=payload.get("payee_name"),
            employee_id=employee_id,
            supplier_id=supplier_id,
            customer_id=as_uuid(payload.get("customer_id")),
            project_id=as_uuid(payload.get("project_id")),
            asset_id=as_uuid(payload.get("asset_id")),
            supplier_invoice_no=payload.get("supplier_invoice_no"),
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            reference=payload.get("reference"),
            notes=payload.get("notes"),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(expense)
        self.db.flush()
        self.apply_line_rows(expense, rows)
        self.apply_totals(
            expense,
            totals,
            discount_amount=money(payload.get("discount_amount")),
            other_charges=money(payload.get("other_charges")),
            exchange_rate=exchange_rate,
        )
        self.audit.log_create(expense, entity_type="expense", label=expense.document_no)
        return expense

    def validate_posting(self, document: Expense) -> None:
        super().validate_posting(document)
        if document.project_id is None:
            category = self.db.get(ExpenseCategory, document.category_id) if document.category_id else None
            if category is not None and category.requires_project:
                raise BusinessRuleError("This expense category requires a project")
        self._assert_budget(document)

    def _assert_budget(self, document: Expense) -> None:
        """Block posting when the linked budget line has no remaining room."""
        if document.project_id is None:
            return
        line_budget = self.db.execute(
            select(BudgetLine)
            .join(Budget, Budget.id == BudgetLine.budget_id)
            .where(
                BudgetLine.company_id == self.company_id,
                Budget.project_id == document.project_id,
                Budget.status == "active",
            )
        ).scalars().first()
        if line_budget is None:
            return
        remaining = money(
            Decimal(line_budget.budget_amount or 0)
            - Decimal(line_budget.actual_amount or 0)
            - Decimal(line_budget.committed_amount or 0)
        )
        amount = money(document.subtotal)
        if amount > remaining:
            raise BusinessRuleError(
                "The expense exceeds the remaining project budget",
                requested=str(amount),
                remaining=str(remaining),
            )

    # ---------------------------------------------------------------- posting
    def build_journal_lines(self, document: Expense, inventory_result: Any = None) -> list[EntryLine]:
        payable_account = self._payable_account(document)
        expense_default = self.posting.resolve_account(
            "purchase_expense", document_type=self.document_type, fallback_code="6110"
        )
        tax_receivable = self.posting.resolve_account(
            "tax_receivable", document_type=self.document_type, fallback_code="1410"
        )
        lines: list[EntryLine] = [
            EntryLine(
                account_id=payable_account.id,
                credit=money(document.total_amount),
                description=f"Expense {document.document_no}",
                party_type=document.payee_type,
                party_id=document.payee_id,
                branch_id=document.branch_id,
                currency_code=document.currency_code,
                exchange_rate=Decimal(document.exchange_rate or 1),
            )
        ]
        for line in document.lines:
            net = money(line.net_amount)
            if net <= 0:
                continue
            cost_account_id = (
                line.expense_account_id
                or (self.db.get(ExpenseCategory, document.category_id).expense_account_id if document.category_id else None)
                or expense_default.id
            )
            lines.append(
                EntryLine(
                    account_id=cost_account_id,
                    debit=net,
                    description=line.description or f"Expense {document.document_no}",
                    project_id=line.project_id or document.project_id,
                    cost_center_id=line.cost_center_id,
                    branch_id=document.branch_id,
                    source_document_line_id=line.id,
                )
            )
            tax_amount = money(line.tax_amount)
            if tax_amount > 0 and (line.tax_recoverable is None or line.tax_recoverable):
                lines.append(
                    EntryLine(
                        account_id=tax_receivable.id,
                        debit=tax_amount,
                        description="Recoverable tax",
                        branch_id=document.branch_id,
                    )
                )
        if money(document.other_charges) > 0:
            lines.append(
                EntryLine(
                    account_id=expense_default.id,
                    debit=money(document.other_charges),
                    description="Other charges",
                    branch_id=document.branch_id,
                )
            )
        return lines

    def _payable_account(self, document: Expense) -> Any:
        if document.supplier_id:
            supplier = self.db.get(Supplier, document.supplier_id)
            if supplier is not None and supplier.payable_account_id:
                return self.posting.account_by_id(supplier.payable_account_id)
        if document.category_id:
            category = self.db.get(ExpenseCategory, document.category_id)
            if category is not None and category.payable_account_id:
                return self.posting.account_by_id(category.payable_account_id)
        role = "ap" if document.supplier_id else "cash"
        fallback = "2110" if document.supplier_id else "1110"
        return self.posting.resolve_account(role, document_type=self.document_type, fallback_code=fallback)

    def after_post(self, document: Expense, inventory_result: Any = None, entry: Any = None) -> None:
        self.posting.refresh_payment_status(document)
        if document.supplier_id:
            self.posting.post_supplier_document(
                supplier_id=document.supplier_id,
                document_type="expense",
                document_id=document.id,
                document_no=document.document_no,
                document_date=document.document_date,
                amount=money(document.total_amount),
                is_credit=True,
                due_date=document.due_date,
                currency_code=document.currency_code,
                exchange_rate=Decimal(document.exchange_rate or 1),
                journal_entry_line_id=entry.lines[0].id if entry and entry.lines else None,
            )
        self._update_budget(document, committed=False)
        self._update_project(document)
        self.db.flush()

    def _update_budget(self, document: Expense, *, committed: bool) -> None:
        if document.project_id is None:
            return
        line_budget = self.db.execute(
            select(BudgetLine)
            .join(Budget, Budget.id == BudgetLine.budget_id)
            .where(
                BudgetLine.company_id == self.company_id,
                Budget.project_id == document.project_id,
                Budget.status == "active",
            )
        ).scalars().first()
        if line_budget is None:
            return
        amount = money(document.subtotal)
        if committed:
            line_budget.committed_amount = money(Decimal(line_budget.committed_amount or 0) + amount)
        else:
            line_budget.actual_amount = money(Decimal(line_budget.actual_amount or 0) + amount)
            line_budget.committed_amount = money(max(Decimal(line_budget.committed_amount or 0) - amount, ZERO))
        budget = self.db.get(Budget, line_budget.budget_id)
        if budget is not None:
            budget.actual_amount = money(Decimal(budget.actual_amount or 0) + amount)
        self.db.flush()

    def _update_project(self, document: Expense) -> None:
        if document.project_id is None:
            return
        from app.models.projects import Project

        project = self.db.get(Project, document.project_id)
        if project is None:
            return
        project.actual_expenses = money(Decimal(project.actual_expenses or 0) + money(document.subtotal))
        self.db.flush()

    # --------------------------------------------------------------- workflow
    def submit(self, document: Any) -> Any:  # type: ignore[override]
        expense = super().submit(document)
        self._update_budget(expense, committed=True)
        return expense

    def pay(self, expense_id: uuid.UUID, payload: dict[str, Any] | None = None) -> Any:
        """Settle a posted expense through the treasury module."""
        from app.services.treasury_service import TreasuryService

        payload = payload or {}
        expense = self.get_document(expense_id)
        if expense.status != DocumentStatus.POSTED.value:
            raise BusinessRuleError("Only posted expenses can be paid")
        if money(expense.balance_amount) <= 0:
            raise BusinessRuleError("This expense is already settled")
        treasury = TreasuryService(self.db, self.company_id, user_id=self.user_id)
        payment = treasury.create(
            {
                "direction": PaymentDirection.OUTBOUND.value,
                "payment_method": payload.get("payment_method", PaymentMethod.CASH.value),
                "document_date": payload.get("document_date") or date.today(),
                "amount": money(payload.get("amount") or expense.balance_amount),
                "party_type": expense.payee_type,
                "party_id": str(expense.payee_id) if expense.payee_id else None,
                "party_name": expense.payee_name,
                "cash_account_id": payload.get("cash_account_id"),
                "bank_account_id": payload.get("bank_account_id"),
                "branch_id": str(expense.branch_id) if expense.branch_id else None,
                "project_id": str(expense.project_id) if expense.project_id else None,
                "cost_center_id": str(getattr(expense, "cost_center_id", None)) if getattr(expense, "cost_center_id", None) else None,
                "reference": expense.document_no,
                "description": f"Payment of expense {expense.document_no}",
                "allocations": [
                    {
                        "document_type": "expense",
                        "document_id": str(expense.id),
                        "document_no": expense.document_no,
                        "amount": str(money(payload.get("amount") or expense.balance_amount)),
                    }
                ],
            }
        )
        treasury.post(payment)
        expense.paid_amount = money(Decimal(expense.paid_amount or 0) + money(payment.amount))
        expense.is_paid = True
        expense.paid_at = datetime.now(UTC)
        expense.payment_id = payment.id
        self.posting.refresh_payment_status(expense)
        self.db.flush()
        return payment


class ExpenseClaimService(BaseDocumentService):
    """Employee expense claims: submit -> approve -> pay."""

    document_type = "expense_claim"
    model = ExpenseClaim
    line_model = None
    permission_entity = "expense_claim"
    permission_module = "expenses"
    requires_lines = False

    def create(self, payload: dict[str, Any]) -> ExpenseClaim:
        from app.models.hr import Employee

        employee_id = as_uuid(payload["employee_id"])
        employee = self.db.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        claim = ExpenseClaim(
            company_id=self.company_id,
            claim_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            employee_id=employee_id,
            claim_date=payload.get("claim_date") or date.today(),
            purpose=payload.get("purpose"),
            total_amount=money(payload.get("total_amount")),
            currency_code=payload.get("currency_code") or employee.currency_code,
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(claim)
        self.db.flush()
        expense_payloads = payload.get("expenses") or []
        total = ZERO
        for item in expense_payloads:
            item = dict(item)
            item.update(
                {
                    "expense_type": "employee_claim",
                    "payee_type": PartyType.EMPLOYEE.value,
                    "payee_id": str(employee_id),
                    "employee_id": str(employee_id),
                    "claim_id": str(claim.id),
                    "document_date": item.get("document_date") or claim.claim_date,
                }
            )
            expense = ExpenseService(self.db, self.company_id, user_id=self.user_id).create(item)
            expense.status = DocumentStatus.SUBMITTED.value
            total += money(expense.total_amount)
        if expense_payloads:
            claim.total_amount = money(total)
        self.db.flush()
        self.audit.log_create(claim, entity_type="expense_claim", label=claim.claim_no)
        return claim

    def approve(self, document: Any) -> Any:  # type: ignore[override]
        claim = super().approve(document)
        claim.status = DocumentStatus.APPROVED.value
        claim.approved_amount = money(claim.approved_amount or claim.total_amount)
        claim.approved_by_id = self.user_id
        claim.approved_at = datetime.now(UTC)
        for expense in claim.expenses:
            expense.status = DocumentStatus.APPROVED.value
        self.db.flush()
        return claim

    def pay(self, claim_id: uuid.UUID, payload: dict[str, Any] | None = None) -> Any:
        """Pay every approved expense on the claim (single treasury voucher)."""
        from app.services.treasury_service import TreasuryService

        payload = payload or {}
        claim = self.get_document(claim_id)
        if claim.status != DocumentStatus.APPROVED.value:
            raise BusinessRuleError("Only approved claims can be paid")
        paid_total = ZERO
        allocations = []
        treasury = TreasuryService(self.db, self.company_id, user_id=self.user_id)
        for expense in claim.expenses:
            if expense.status != DocumentStatus.APPROVED.value:
                continue
            ExpenseService(self.db, self.company_id, user_id=self.user_id).post(expense)
            allocations.append(
                {
                    "document_type": "expense",
                    "document_id": str(expense.id),
                    "document_no": expense.document_no,
                    "amount": str(money(expense.balance_amount)),
                }
            )
            paid_total += money(expense.balance_amount)
        if not allocations:
            raise BusinessRuleError("There is nothing to pay on this claim")
        payment = treasury.create(
            {
                "direction": PaymentDirection.OUTBOUND.value,
                "payment_method": payload.get("payment_method", PaymentMethod.CASH.value),
                "document_date": payload.get("document_date") or date.today(),
                "amount": money(paid_total),
                "party_type": PartyType.EMPLOYEE.value,
                "party_id": str(claim.employee_id),
                "cash_account_id": payload.get("cash_account_id"),
                "bank_account_id": payload.get("bank_account_id"),
                "reference": claim.claim_no,
                "description": f"Reimbursement of claim {claim.claim_no}",
                "allocations": allocations,
            }
        )
        treasury.post(payment)
        claim.paid_amount = money(paid_total)
        claim.payment_id = payment.id
        claim.status = DocumentStatus.CLOSED.value
        self.db.flush()
        return payment


class ExpenseAdvanceService:
    """Employee cash advances and their settlement against claims."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.posting = PostingService(db, company_id)
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> ExpenseAdvance:
        amount = money(payload.get("amount"))
        if amount <= 0:
            raise ValidationFailure("The advance amount must be greater than zero")
        advance = ExpenseAdvance(
            company_id=self.company_id,
            advance_no=payload.get("advance_no") or self._next_no(),
            employee_id=as_uuid(payload["employee_id"]),
            advance_date=payload.get("advance_date") or date.today(),
            amount=amount,
            settled_amount=ZERO,
            balance_amount=amount,
            purpose=payload.get("purpose"),
            status="draft",
            approved_by_id=as_uuid(payload.get("approved_by_id")),
        )
        self.db.add(advance)
        self.db.flush()
        self.audit.log_create(advance, entity_type="expense_advance", label=advance.advance_no)
        return advance

    def _next_no(self) -> str:
        count = self.db.execute(
            select(func.count()).select_from(ExpenseAdvance).where(ExpenseAdvance.company_id == self.company_id)
        ).scalar_one()
        return f"ADV-{int(count) + 1:05d}"

    def approve_and_pay(self, advance_id: uuid.UUID, payload: dict[str, Any] | None = None) -> ExpenseAdvance:
        from app.services.treasury_service import TreasuryService

        payload = payload or {}
        advance = self.db.execute(
            select(ExpenseAdvance).where(
                ExpenseAdvance.company_id == self.company_id, ExpenseAdvance.id == advance_id
            )
        ).scalars().first()
        if advance is None:
            raise NotFoundError("Advance not found")
        if advance.status != "draft":
            raise BusinessRuleError("Only draft advances can be paid")
        treasury = TreasuryService(self.db, self.company_id, user_id=self.user_id)
        payment = treasury.create(
            {
                "direction": PaymentDirection.OUTBOUND.value,
                "payment_method": payload.get("payment_method", PaymentMethod.CASH.value),
                "document_date": payload.get("document_date") or advance.advance_date,
                "amount": money(advance.amount),
                "party_type": PartyType.EMPLOYEE.value,
                "party_id": str(advance.employee_id),
                "cash_account_id": payload.get("cash_account_id"),
                "bank_account_id": payload.get("bank_account_id"),
                "reference": advance.advance_no,
                "description": f"Advance {advance.advance_no}",
            }
        )
        treasury.post(payment)
        advance.status = "paid"
        advance.approved_by_id = self.user_id
        advance.payment_id = payment.id
        self.db.flush()
        return advance

    def settle(self, advance_id: uuid.UUID, *, amount: Decimal, notes: str | None = None) -> ExpenseAdvance:
        advance = self.db.execute(
            select(ExpenseAdvance).where(
                ExpenseAdvance.company_id == self.company_id, ExpenseAdvance.id == advance_id
            )
        ).scalars().first()
        if advance is None:
            raise NotFoundError("Advance not found")
        settled = money(Decimal(advance.settled_amount or 0) + money(amount))
        if settled > Decimal(advance.amount or 0):
            raise BusinessRuleError("The settlement exceeds the advance amount")
        advance.settled_amount = settled
        advance.balance_amount = money(Decimal(advance.amount or 0) - settled)
        if advance.balance_amount <= 0:
            advance.status = "settled"
        self.db.flush()
        return advance

    def outstanding(self, *, employee_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        stmt = select(ExpenseAdvance).where(
            ExpenseAdvance.company_id == self.company_id,
            ExpenseAdvance.balance_amount > 0,
        )
        if employee_id:
            stmt = stmt.where(ExpenseAdvance.employee_id == employee_id)
        rows = list(self.db.execute(stmt).scalars().all())
        return [
            {
                "advance_no": item.advance_no,
                "employee_id": str(item.employee_id),
                "advance_date": item.advance_date.isoformat(),
                "amount": str(money(item.amount)),
                "settled": str(money(item.settled_amount)),
                "balance": str(money(item.balance_amount)),
                "status": item.status,
            }
            for item in rows
        ]


class BudgetService:
    """Budget definition and budget-vs-actual control."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> Budget:
        code = str(payload["code"]).strip().upper()
        if self.db.execute(
            select(Budget).where(Budget.company_id == self.company_id, Budget.code == code)
        ).scalars().first():
            raise ConflictError(f"Budget {code} already exists")
        budget = Budget(
            company_id=self.company_id,
            code=code,
            name=payload["name"],
            fiscal_year_id=as_uuid(payload.get("fiscal_year_id")),
            scope_type=payload.get("scope_type", "company"),
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            project_id=as_uuid(payload.get("project_id")),
            start_date=payload["start_date"],
            end_date=payload["end_date"],
            total_amount=money(payload.get("total_amount")),
            status=payload.get("status", "active"),
        )
        self.db.add(budget)
        self.db.flush()
        for line in payload.get("lines", []):
            self.db.add(
                BudgetLine(
                    company_id=self.company_id,
                    budget_id=budget.id,
                    account_id=as_uuid(line.get("account_id")),
                    cost_center_id=as_uuid(line.get("cost_center_id")),
                    project_id=as_uuid(line.get("project_id")),
                    period_year=int(line.get("period_year") or budget.start_date.year),
                    period_month=int(line.get("period_month") or 0),
                    budget_amount=money(line.get("budget_amount")),
                )
            )
        if budget.total_amount == 0:
            budget.total_amount = money(
                sum((Decimal(line.budget_amount or 0) for line in budget.lines), ZERO)
            )
        self.db.flush()
        self.audit.log_create(budget, entity_type="budget", label=budget.code)
        return budget

    def commit(self, budget_id: uuid.UUID, *, budget_line_id: uuid.UUID, amount: Decimal) -> BudgetLine:
        line = self.db.execute(
            select(BudgetLine).where(
                BudgetLine.company_id == self.company_id,
                BudgetLine.budget_id == budget_id,
                BudgetLine.id == budget_line_id,
            )
        ).scalars().first()
        if line is None:
            raise NotFoundError("Budget line not found")
        line.committed_amount = money(Decimal(line.committed_amount or 0) + money(amount))
        self.db.flush()
        return line

    def report(self, budget_id: uuid.UUID) -> dict[str, Any]:
        budget = self.db.execute(
            select(Budget).where(Budget.company_id == self.company_id, Budget.id == budget_id)
        ).scalars().first()
        if budget is None:
            raise NotFoundError("Budget not found")
        lines = []
        for line in budget.lines:
            budget_amount = money(line.budget_amount)
            actual = money(line.actual_amount)
            committed = money(line.committed_amount)
            variance = money(budget_amount - actual - committed)
            lines.append(
                {
                    "line_id": str(line.id),
                    "account_id": str(line.account_id) if line.account_id else None,
                    "period": f"{line.period_year}-{line.period_month:02d}" if line.period_month else str(line.period_year),
                    "budget": str(budget_amount),
                    "actual": str(actual),
                    "committed": str(committed),
                    "available": str(variance),
                    "usage_percent": str(
                        ((actual + committed) / budget_amount * 100).quantize(Decimal("0.01"))
                        if budget_amount
                        else ZERO
                    ),
                }
            )
        return {
            "budget": {
                "code": budget.code,
                "name": budget.name,
                "total_amount": str(money(budget.total_amount)),
                "actual_amount": str(money(budget.actual_amount)),
                "committed_amount": str(money(budget.committed_amount)),
                "status": budget.status,
            },
            "lines": lines,
        }

    def check_availability(
        self, *, project_id: uuid.UUID | None = None, account_id: uuid.UUID | None = None, amount: Decimal = ZERO
    ) -> dict[str, Any]:
        """Return whether a planned spend fits the active budget."""
        stmt = (
            select(BudgetLine)
            .join(Budget, Budget.id == BudgetLine.budget_id)
            .where(BudgetLine.company_id == self.company_id, Budget.status == "active")
        )
        if project_id:
            stmt = stmt.where(Budget.project_id == project_id)
        if account_id:
            stmt = stmt.where(BudgetLine.account_id == account_id)
        lines = list(self.db.execute(stmt).scalars().all())
        if not lines:
            return {"budgeted": False, "allowed": True, "remaining": None}
        remaining = money(
            sum(
                (
                    Decimal(line.budget_amount or 0)
                    - Decimal(line.actual_amount or 0)
                    - Decimal(line.committed_amount or 0)
                    for line in lines
                ),
                ZERO,
            )
        )
        return {
            "budgeted": True,
            "allowed": money(amount) <= remaining,
            "remaining": str(remaining),
            "requested": str(money(amount)),
        }
