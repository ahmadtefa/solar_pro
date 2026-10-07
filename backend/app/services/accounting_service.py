"""Accounting services: chart of accounts, journal entries, fiscal calendar,
period close and FX revaluation helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import (
    AccountType,
    AuditAction,
    CashFlowCategory,
    DocumentStatus,
    NormalBalance,
    PartyType,
)
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.accounting import (
    Account,
    AccountingPeriodClose,
    JournalEntry,
    JournalEntryLine,
    PostingRule,
)
from app.models.platform import FiscalPeriod, FiscalYear
from app.models.treasury import BankAccount, CashAccount
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.posting_service import (
    NORMAL_BALANCE_FOR_TYPE,
    EntryLine,
    PostingService,
    money,
)

#: Default chart of accounts created for a new company.  Companies can edit it
#: freely; nothing in the code depends on a specific code beyond these defaults.
CHART_TEMPLATE: list[dict[str, Any]] = [
    # (code, name, name_ar, type, is_group)
    {"code": "1", "name": "Assets", "name_ar": "الأصول", "type": AccountType.ASSET, "group": True},
    {"code": "11", "name": "Current Assets", "name_ar": "الأصول المتداولة", "type": AccountType.ASSET, "group": True},
    {"code": "1110", "name": "Cash on Hand", "name_ar": "النقدية بالصندوق", "type": AccountType.ASSET, "cash": True},
    {"code": "1120", "name": "Banks", "name_ar": "البنوك", "type": AccountType.ASSET, "bank": True},
    {"code": "1130", "name": "Cheques Under Collection", "name_ar": "شيكات برسم التحصيل", "type": AccountType.ASSET},
    {"code": "1210", "name": "Accounts Receivable", "name_ar": "العملاء (مدينون)", "type": AccountType.ASSET, "control": True, "party": PartyType.CUSTOMER.value},
    {"code": "1215", "name": "Allowance for Doubtful Debts", "name_ar": "مخصص الديون المشكوك فيها", "type": AccountType.ASSET},
    {"code": "1310", "name": "Inventory", "name_ar": "المخزون", "type": AccountType.ASSET},
    {"code": "1320", "name": "Work In Progress", "name_ar": "إنتاج تام غير منجز", "type": AccountType.ASSET},
    {"code": "1330", "name": "Accumulated Depreciation", "name_ar": "مجمع الإهلاك", "type": AccountType.ASSET},
    {"code": "1410", "name": "VAT Input (Recoverable)", "name_ar": "ضريبة القيمة المضافة - مدخلات", "type": AccountType.ASSET, "tax": True},
    {"code": "1420", "name": "Employee Advances", "name_ar": "سلف العاملين", "type": AccountType.ASSET},
    {"code": "1430", "name": "Prepaid Expenses", "name_ar": "مصروفات مدفوعة مقدماً", "type": AccountType.ASSET},
    {"code": "15", "name": "Fixed Assets", "name_ar": "الأصول الثابتة", "type": AccountType.ASSET, "group": True},
    {"code": "1510", "name": "Property, Plant and Equipment", "name_ar": "الأصول الثابتة", "type": AccountType.ASSET},
    {"code": "2", "name": "Liabilities", "name_ar": "الالتزامات", "type": AccountType.LIABILITY, "group": True},
    {"code": "2110", "name": "Accounts Payable", "name_ar": "الموردون (دائنون)", "type": AccountType.LIABILITY, "control": True, "party": PartyType.SUPPLIER.value},
    {"code": "2120", "name": "Customer Advances", "name_ar": "دفعات مقدمة من العملاء", "type": AccountType.LIABILITY},
    {"code": "2130", "name": "Goods Received Not Invoiced", "name_ar": "بضاعة مستلمة لم تفتر بفاتورة", "type": AccountType.LIABILITY},
    {"code": "2140", "name": "Accrued Expenses", "name_ar": "مصروفات مستحقة", "type": AccountType.LIABILITY},
    {"code": "2210", "name": "VAT Output (Payable)", "name_ar": "ضريبة القيمة المضافة - مخرجات", "type": AccountType.LIABILITY, "tax": True},
    {"code": "2220", "name": "Withholding Tax Payable", "name_ar": "ضريبة خصم المنبع", "type": AccountType.LIABILITY, "tax": True},
    {"code": "2230", "name": "Salaries Payable", "name_ar": "رواتب مستحقة", "type": AccountType.LIABILITY},
    {"code": "2240", "name": "Payroll Tax Payable", "name_ar": "ضرائب كسب عمل مستحقة", "type": AccountType.LIABILITY},
    {"code": "2250", "name": "Social Insurance Payable", "name_ar": "تأمينات اجتماعية مستحقة", "type": AccountType.LIABILITY},
    {"code": "23", "name": "Long Term Liabilities", "name_ar": "التزامات طويلة الأجل", "type": AccountType.LIABILITY, "group": True},
    {"code": "2310", "name": "Long Term Loans", "name_ar": "قروض طويلة الأجل", "type": AccountType.LIABILITY},
    {"code": "3", "name": "Equity", "name_ar": "حقوق الملكية", "type": AccountType.EQUITY, "group": True},
    {"code": "3110", "name": "Retained Earnings", "name_ar": "الأرباح المحتجزة", "type": AccountType.EQUITY},
    {"code": "3120", "name": "Capital", "name_ar": "رأس المال", "type": AccountType.EQUITY},
    {"code": "3130", "name": "Owner Drawings", "name_ar": "مسحوبات المالك", "type": AccountType.EQUITY},
    {"code": "4", "name": "Revenue", "name_ar": "الإيرادات", "type": AccountType.REVENUE, "group": True},
    {"code": "4110", "name": "Sales Revenue", "name_ar": "إيرادات المبيعات", "type": AccountType.REVENUE},
    {"code": "4120", "name": "Sales Discounts", "name_ar": "خصم مسموح به", "type": AccountType.REVENUE},
    {"code": "4130", "name": "Shipping & Other Revenue", "name_ar": "إيرادات الشحن والخدمات", "type": AccountType.REVENUE},
    {"code": "4140", "name": "Service Revenue", "name_ar": "إيرادات الخدمات", "type": AccountType.REVENUE},
    {"code": "4210", "name": "Foreign Exchange Gain", "name_ar": "أرباح فروق العملة", "type": AccountType.REVENUE},
    {"code": "4220", "name": "Rounding Gain", "name_ar": "أرباح فروق التقريب", "type": AccountType.REVENUE},
    {"code": "4230", "name": "Asset Disposal Gain", "name_ar": "أرباح بيع أصول", "type": AccountType.REVENUE},
    {"code": "5", "name": "Cost of Sales", "name_ar": "تكلفة المبيعات", "type": AccountType.EXPENSE, "group": True},
    {"code": "5110", "name": "Cost of Goods Sold", "name_ar": "تكلفة البضاعة المباعة", "type": AccountType.EXPENSE},
    {"code": "5120", "name": "Manufacturing Cost", "name_ar": "تكلفة التصنيع", "type": AccountType.EXPENSE},
    {"code": "5130", "name": "Purchases", "name_ar": "المشتريات", "type": AccountType.EXPENSE},
    {"code": "5140", "name": "Purchase Discounts Received", "name_ar": "خصم مكتسب", "type": AccountType.EXPENSE},
    {"code": "5150", "name": "Freight In", "name_ar": "مصاريف نقل مشتريات", "type": AccountType.EXPENSE},
    {"code": "5160", "name": "Inventory Adjustment", "name_ar": "تسويات المخزون", "type": AccountType.EXPENSE},
    {"code": "5170", "name": "Scrap & Wastage", "name_ar": "الهوالك والتالف", "type": AccountType.EXPENSE},
    {"code": "5180", "name": "Manufacturing Overhead", "name_ar": "تكاليف صناعية غير مباشرة", "type": AccountType.EXPENSE},
    {"code": "5210", "name": "Foreign Exchange Loss", "name_ar": "خسائر فروق العملة", "type": AccountType.EXPENSE},
    {"code": "5220", "name": "Asset Disposal Loss", "name_ar": "خسائر بيع أصول", "type": AccountType.EXPENSE},
    {"code": "6", "name": "Operating Expenses", "name_ar": "المصروفات التشغيلية", "type": AccountType.EXPENSE, "group": True},
    {"code": "6110", "name": "Salaries & Wages", "name_ar": "الرواتب والأجور", "type": AccountType.EXPENSE},
    {"code": "6115", "name": "Employee Benefits", "name_ar": "مزايا العاملين", "type": AccountType.EXPENSE},
    {"code": "6120", "name": "Depreciation Expense", "name_ar": "مصروف الإهلاك", "type": AccountType.EXPENSE},
    {"code": "6130", "name": "Employee Expense Claims", "name_ar": "مطالبات مصروفات العاملين", "type": AccountType.EXPENSE},
    {"code": "6210", "name": "Rent", "name_ar": "إيجارات", "type": AccountType.EXPENSE},
    {"code": "6220", "name": "Utilities", "name_ar": "مرافق وخدمات", "type": AccountType.EXPENSE},
    {"code": "6230", "name": "Telecommunications", "name_ar": "اتصالات", "type": AccountType.EXPENSE},
    {"code": "6240", "name": "Fuel & Transportation", "name_ar": "وقود ومواصلات", "type": AccountType.EXPENSE},
    {"code": "6250", "name": "Marketing & Advertising", "name_ar": "تسويق وإعلان", "type": AccountType.EXPENSE},
    {"code": "6260", "name": "Professional Fees", "name_ar": "أتعاب مهنية", "type": AccountType.EXPENSE},
    {"code": "6270", "name": "Office Supplies", "name_ar": "أدوات مكتبية", "type": AccountType.EXPENSE},
    {"code": "6280", "name": "Maintenance & Repairs", "name_ar": "صيانة وإصلاح", "type": AccountType.EXPENSE},
    {"code": "6290", "name": "Bank Charges", "name_ar": "مصاريف بنكية", "type": AccountType.EXPENSE},
    {"code": "6300", "name": "Insurance", "name_ar": "تأمينات", "type": AccountType.EXPENSE},
    {"code": "6310", "name": "Travel & Accommodation", "name_ar": "سفر وإقامة", "type": AccountType.EXPENSE},
    {"code": "6320", "name": "Government Fees & Licenses", "name_ar": "رسوم حكومية", "type": AccountType.EXPENSE},
    {"code": "6330", "name": "Software & Subscriptions", "name_ar": "برمجيات واشتراكات", "type": AccountType.EXPENSE},
    {"code": "9999", "name": "Suspense Account", "name_ar": "حساب معلق", "type": AccountType.ASSET},
]


class ChartOfAccountsService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id
        self.audit = AuditService(db, AuditContext(company_id=company_id))

    # ------------------------------------------------------------ bootstrap
    def create_standard_chart(self) -> dict[str, uuid.UUID]:
        """Create the default chart of accounts (idempotent)."""
        created: dict[str, uuid.UUID] = {}
        parent_by_prefix: dict[str, Account] = {}
        for entry in CHART_TEMPLATE:
            existing = self.db.execute(
                select(Account).where(Account.company_id == self.company_id, Account.code == entry["code"])
            ).scalars().first()
            if existing is not None:
                created[entry["code"]] = existing.id
                parent_by_prefix[entry["code"]] = existing
                continue
            account_type = entry["type"]
            parent = self._parent_for(entry["code"], parent_by_prefix)
            account = Account(
                company_id=self.company_id,
                code=entry["code"],
                name=entry["name"],
                name_ar=entry.get("name_ar"),
                account_type=account_type.value,
                normal_balance=NORMAL_BALANCE_FOR_TYPE[account_type.value],
                parent_id=parent.id if parent else None,
                level=(parent.level + 1) if parent else 1,
                path=f"{parent.path}/{entry['code']}" if parent and parent.path else entry["code"],
                is_group=bool(entry.get("group", False)),
                is_postable=not bool(entry.get("group", False)),
                is_cash_account=bool(entry.get("cash", False)),
                is_bank_account=bool(entry.get("bank", False)),
                is_control_account=bool(entry.get("control", False)),
                is_tax_account=bool(entry.get("tax", False)),
                requires_party=bool(entry.get("party")),
                party_type=entry.get("party"),
                cash_flow_category=(
                    CashFlowCategory.OPERATING.value
                    if account_type in {AccountType.REVENUE, AccountType.EXPENSE}
                    else CashFlowCategory.FINANCING.value
                ),
            )
            self.db.add(account)
            self.db.flush()
            created[entry["code"]] = account.id
            parent_by_prefix[entry["code"]] = account
        self.db.flush()
        return created

    def _parent_for(self, code: str, registry: dict[str, Account]) -> Account | None:
        """Find the closest existing parent by code prefix."""
        for length in range(len(code) - 1, 0, -1):
            prefix = code[:length]
            if prefix in registry:
                return registry[prefix]
        return None

    def create_cash_account(
        self,
        *,
        name: str,
        code: str,
        branch_id: uuid.UUID | None = None,
        opening_balance: Decimal = Decimal("0"),
        currency_code: str | None = None,
        custodian_id: uuid.UUID | None = None,
    ) -> CashAccount:
        chart = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.code == "1110")
        ).scalars().first()
        if chart is None:
            chart_id = self.create_standard_chart().get("1110")
            chart = self.db.get(Account, chart_id) if chart_id else None
        if chart is None:
            raise BusinessRuleError("Cash account in the chart of accounts is missing")
        cash = CashAccount(
            company_id=self.company_id,
            code=code,
            name=name,
            branch_id=branch_id,
            account_id=chart.id,
            custodian_id=custodian_id,
            currency_code=currency_code,
            opening_balance=money(opening_balance),
            current_balance=money(opening_balance),
        )
        self.db.add(cash)
        self.db.flush()
        return cash

    def create_bank_account(
        self,
        *,
        name: str,
        code: str,
        bank_name: str,
        account_number: str | None = None,
        iban: str | None = None,
        branch_id: uuid.UUID | None = None,
        opening_balance: Decimal = Decimal("0"),
        currency_code: str | None = None,
    ) -> BankAccount:
        chart = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.code == "1120")
        ).scalars().first()
        if chart is None:
            chart_id = self.create_standard_chart().get("1120")
            chart = self.db.get(Account, chart_id) if chart_id else None
        if chart is None:
            raise BusinessRuleError("Bank account in the chart of accounts is missing")
        bank = BankAccount(
            company_id=self.company_id,
            code=code,
            name=name,
            bank_name=bank_name,
            account_number=account_number,
            iban=iban,
            branch_id=branch_id,
            account_id=chart.id,
            currency_code=currency_code,
            opening_balance=money(opening_balance),
            current_balance=money(opening_balance),
        )
        self.db.add(bank)
        self.db.flush()
        return bank

    # ------------------------------------------------------------- accounts
    def create_account(self, payload: dict[str, Any]) -> Account:
        code = str(payload["code"]).strip()
        existing = self.db.execute(
            select(Account).where(Account.company_id == self.company_id, Account.code == code)
        ).scalars().first()
        if existing is not None:
            raise ConflictError(f"An account with code {code} already exists")
        account_type = AccountType(str(payload.get("account_type", AccountType.ASSET.value)))
        parent = None
        if as_uuid(payload.get("parent_id")):
            parent = self.db.get(Account, uuid.UUID(str(payload["parent_id"])))
            if parent is None:
                raise NotFoundError("Parent account not found")
        account = Account(
            company_id=self.company_id,
            code=code,
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            account_type=account_type.value,
            normal_balance=str(payload.get("normal_balance") or NORMAL_BALANCE_FOR_TYPE[account_type.value]),
            parent_id=parent.id if parent else None,
            level=(parent.level + 1) if parent else 1,
            path=f"{parent.path}/{code}" if parent and parent.path else code,
            is_group=bool(payload.get("is_group", False)),
            is_postable=not bool(payload.get("is_group", False)),
            allow_manual_entries=bool(payload.get("allow_manual_entries", True)),
            requires_cost_center=bool(payload.get("requires_cost_center", False)),
            requires_party=bool(payload.get("requires_party", False)),
            party_type=payload.get("party_type"),
            currency_code=payload.get("currency_code"),
            cash_flow_category=payload.get("cash_flow_category"),
            is_tax_account=bool(payload.get("is_tax_account", False)),
            opening_balance=money(payload.get("opening_balance")),
            description=payload.get("description"),
        )
        self.db.add(account)
        self.db.flush()
        self.audit.log_create(account, entity_type="account", label=account.code)
        return account

    def tree(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        stmt = select(Account).where(Account.company_id == self.company_id)
        if not include_inactive:
            stmt = stmt.where(Account.is_active.is_(True))
        accounts = list(self.db.execute(stmt.order_by(Account.code)).scalars().all())
        balances = PostingService(self.db, self.company_id).account_balance_map()
        nodes: dict[uuid.UUID, dict[str, Any]] = {}
        roots: list[dict[str, Any]] = []
        for account in accounts:
            debit, credit = balances.get(account.id, (Decimal("0"), Decimal("0")))
            node = {
                "id": account.id,
                "code": account.code,
                "name": account.name,
                "name_ar": account.name_ar,
                "account_type": account.account_type,
                "normal_balance": account.normal_balance,
                "is_group": account.is_group,
                "is_postable": account.is_postable,
                "is_active": account.is_active,
                "currency_code": account.currency_code,
                "debit": str(debit),
                "credit": str(credit),
                "balance": str(
                    debit - credit
                    if account.normal_balance == NormalBalance.DEBIT.value
                    else credit - debit
                ),
                "children": [],
            }
            nodes[account.id] = node
        for account in accounts:
            node = nodes[account.id]
            if account.parent_id and account.parent_id in nodes:
                nodes[account.parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def account_balances(self, *, date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
        posting = PostingService(self.db, self.company_id)
        accounts = list(
            self.db.execute(
                select(Account).where(Account.company_id == self.company_id, Account.is_active.is_(True)).order_by(Account.code)
            ).scalars().all()
        )
        rows: list[dict[str, Any]] = []
        for account in accounts:
            debit, credit = posting.account_balance(account.id, date_from=date_from, date_to=date_to)
            if account.normal_balance == NormalBalance.DEBIT.value:
                balance = debit - credit
            else:
                balance = credit - debit
            rows.append(
                {
                    "account_id": account.id,
                    "code": account.code,
                    "name": account.name,
                    "name_ar": account.name_ar,
                    "account_type": account.account_type,
                    "normal_balance": account.normal_balance,
                    "is_group": account.is_group,
                    "debit": str(debit),
                    "credit": str(credit),
                    "balance": str(balance),
                }
            )
        return rows


class FiscalCalendarService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id

    def create_year(
        self, *, start_date: date, end_date: date, name: str | None = None, generate_periods: bool = True
    ) -> FiscalYear:
        overlap = self.db.execute(
            select(FiscalYear).where(
                FiscalYear.company_id == self.company_id,
                FiscalYear.start_date <= end_date,
                FiscalYear.end_date >= start_date,
                FiscalYear.is_closed.is_(False),
            )
        ).scalars().first()
        if overlap is not None:
            raise ConflictError("A fiscal year already covers this period", existing=overlap.code)
        year = FiscalYear(
            company_id=self.company_id,
            code=str(start_date.year),
            name=name or f"Fiscal Year {start_date.year}",
            start_date=start_date,
            end_date=end_date,
            status="open",
        )
        self.db.add(year)
        self.db.flush()
        if generate_periods:
            self.generate_monthly_periods(year)
        return year

    def generate_monthly_periods(self, fiscal_year: FiscalYear) -> list[FiscalPeriod]:
        periods: list[FiscalPeriod] = []
        cursor = fiscal_year.start_date
        index = 1
        while cursor <= fiscal_year.end_date:
            if cursor.month == 12:
                month_end = date(cursor.year, 12, 31)
            else:
                month_end = date(cursor.year, cursor.month + 1, 1) - timedelta(days=1)
            period_end = min(month_end, fiscal_year.end_date)
            period = FiscalPeriod(
                company_id=self.company_id,
                fiscal_year_id=fiscal_year.id,
                period_number=index,
                name=cursor.strftime("%b %Y"),
                start_date=cursor,
                end_date=period_end,
            )
            self.db.add(period)
            periods.append(period)
            cursor = period_end + timedelta(days=1)
            index += 1
        self.db.flush()
        return periods

    def close_period(self, period_id: uuid.UUID, *, reason: str | None = None) -> FiscalPeriod:
        period = self.db.get(FiscalPeriod, period_id)
        if period is None or period.company_id != self.company_id:
            raise NotFoundError("Fiscal period not found")
        if period.is_closed:
            return period
        draft_entries = self.db.execute(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.company_id == self.company_id,
                JournalEntry.fiscal_period_id == period.id,
                JournalEntry.status == DocumentStatus.DRAFT.value,
            )
        ).scalar_one()
        if draft_entries:
            raise BusinessRuleError(
                "The period contains draft journal entries; post or delete them before closing",
                draft_entries=int(draft_entries),
            )
        period.is_closed = True
        period.closed_at = datetime.now(UTC)
        self.db.flush()
        return period

    def reopen_period(self, period_id: uuid.UUID, *, reason: str) -> FiscalPeriod:
        period = self.db.get(FiscalPeriod, period_id)
        if period is None or period.company_id != self.company_id:
            raise NotFoundError("Fiscal period not found")
        period.is_closed = False
        period.closed_at = None
        self.db.flush()
        return period


class JournalEntryService(BaseDocumentService):
    document_type = "journal_entry"
    model = JournalEntry
    line_model = JournalEntryLine
    permission_module = "accounting"
    permission_entity = "journal_entry"
    requires_lines = True

    def create(self, payload: dict[str, Any]) -> JournalEntry:
        entry_date = payload.get("entry_date") or date.today()
        raw_lines = payload.get("lines") or []
        if len(raw_lines) < 2:
            raise ValidationFailure("A journal entry requires at least two lines")
        lines: list[EntryLine] = []
        for raw in raw_lines:
            account_id = uuid.UUID(str(raw["account_id"]))
            lines.append(
                EntryLine(
                    account_id=account_id,
                    debit=money(raw.get("debit")),
                    credit=money(raw.get("credit")),
                    description=raw.get("description"),
                    party_type=raw.get("party_type"),
                    party_id=uuid.UUID(str(raw["party_id"])) if raw.get("party_id") else None,
                    branch_id=uuid.UUID(str(raw["branch_id"])) if raw.get("branch_id") else as_uuid(payload.get("branch_id")),
                    department_id=uuid.UUID(str(raw["department_id"])) if raw.get("department_id") else None,
                    cost_center_id=uuid.UUID(str(raw["cost_center_id"])) if raw.get("cost_center_id") else None,
                    project_id=uuid.UUID(str(raw["project_id"])) if raw.get("project_id") else None,
                    currency_code=raw.get("currency_code"),
                    exchange_rate=Decimal(str(raw.get("exchange_rate") or 1)),
                )
            )
        entry = self.posting.build_entry(
            context=self._manual_context(payload, entry_date),
            lines=lines,
            entry_type=payload.get("entry_type", "manual"),
            reference=payload.get("reference"),
            auto_post=bool(payload.get("auto_post", False)),
            user_id=self.user_id,
        )
        return entry

    def _manual_context(self, payload: dict[str, Any], entry_date: date):
        from app.services.posting_service import DocumentPostingContext

        return DocumentPostingContext(
            document_type="journal_entry",
            document_id=uuid.uuid4(),
            document_no=payload.get("reference") or "MANUAL",
            document_date=entry_date,
            description=payload.get("description"),
            branch_id=as_uuid(payload.get("branch_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=Decimal(str(payload.get("exchange_rate") or 1)),
        )

    def reverse(self, entry_id: uuid.UUID, *, reason: str, reversal_date: date | None = None) -> JournalEntry:
        entry = self.get_document(entry_id)
        return self.posting.reverse_entry(entry, reason=reason, reversal_date=reversal_date, user_id=self.user_id)


class PeriodCloseService:
    """Year end close: transfer the net result to retained earnings."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.posting = PostingService(db, company_id)
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def net_result(self, fiscal_year: FiscalYear) -> tuple[Decimal, Decimal, Decimal]:
        """Return ``(revenue, expense, net_profit)`` for a fiscal year."""
        rows = self.db.execute(
            select(
                Account.account_type,
                func.coalesce(func.sum(JournalEntryLine.credit - JournalEntryLine.debit), 0),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                Account.company_id == self.company_id,
                JournalEntry.entry_date >= fiscal_year.start_date,
                JournalEntry.entry_date <= fiscal_year.end_date,
                JournalEntry.status == DocumentStatus.POSTED.value,
                Account.account_type.in_([AccountType.REVENUE.value, AccountType.EXPENSE.value]),
            )
            .group_by(Account.account_type)
        ).all()
        revenue = Decimal("0")
        expense = Decimal("0")
        for account_type, value in rows:
            if account_type == AccountType.REVENUE.value:
                revenue = money(value)
            else:
                expense = money(-Decimal(value))
        return revenue, expense, money(revenue - expense)

    def close_year(self, fiscal_year_id: uuid.UUID, *, retained_earnings_account_id: uuid.UUID | None = None) -> dict[str, Any]:
        fiscal_year = self.db.get(FiscalYear, fiscal_year_id)
        if fiscal_year is None or fiscal_year.company_id != self.company_id:
            raise NotFoundError("Fiscal year not found")
        if fiscal_year.is_closed:
            raise BusinessRuleError("This fiscal year is already closed")
        open_periods = [period for period in fiscal_year.periods if not period.is_closed]
        revenue, expense, net_profit = self.net_result(fiscal_year)

        retained = (
            self.posting.account_by_id(retained_earnings_account_id)
            if retained_earnings_account_id
            else self.posting.resolve_account("retained_earnings", document_type="period_close", fallback_code="3110")
        )
        entries: list[JournalEntry] = []
        if net_profit != 0:
            lines = [
                EntryLine(
                    account_id=retained.id,
                    credit=net_profit if net_profit > 0 else Decimal("0"),
                    debit=abs(net_profit) if net_profit < 0 else Decimal("0"),
                    description=f"Transfer of result for {fiscal_year.code}",
                )
            ]
            # Offset against each revenue/expense account so the ledger is cleared.
            balances = self.posting.account_balance_map()
            for account in self.db.execute(
                select(Account).where(
                    Account.company_id == self.company_id,
                    Account.account_type.in_([AccountType.REVENUE.value, AccountType.EXPENSE.value]),
                    Account.is_postable.is_(True),
                )
            ).scalars().all():
                debit, credit = balances.get(account.id, (Decimal("0"), Decimal("0")))
                net = money(credit - debit)
                if net == 0:
                    continue
                lines.append(
                    EntryLine(
                        account_id=account.id,
                        debit=net if net > 0 else Decimal("0"),
                        credit=abs(net) if net < 0 else Decimal("0"),
                        description=f"Closing {account.code}",
                    )
                )
            debits = sum((line.debit for line in lines), Decimal("0"))
            credits = sum((line.credit for line in lines), Decimal("0"))
            difference = money(debits - credits)
            if difference != 0:
                # Balance with the retained earnings account (already included above).
                lines[0].debit = money(lines[0].debit + (difference if difference > 0 else Decimal("0")))
                lines[0].credit = money(lines[0].credit + (-difference if difference < 0 else Decimal("0")))
            entry = self.posting.build_entry(
                context=self._context(fiscal_year),
                lines=lines,
                entry_type="period_close",
                reference=f"CLOSE-{fiscal_year.code}",
                auto_post=True,
                user_id=self.user_id,
            )
            entries.append(entry)

        for period in open_periods:
            period.is_closed = True
            period.closed_at = datetime.now(UTC)
        fiscal_year.is_closed = True
        fiscal_year.status = "closed"
        fiscal_year.closed_at = datetime.now(UTC)
        self.db.add(
            AccountingPeriodClose(
                company_id=self.company_id,
                fiscal_year_id=fiscal_year.id,
                journal_entry_id=entries[0].id if entries else None,
                net_profit=net_profit,
                closed_by_id=self.user_id,
                closed_at=datetime.now(UTC),
                notes=f"Revenue {revenue} / Expense {expense}",
            )
        )
        self.db.flush()
        self.audit.record(
            action=AuditAction.CLOSE,
            entity_type="fiscal_year",
            entity_id=fiscal_year.id,
            entity_label=fiscal_year.code,
            new_values={"net_profit": str(net_profit)},
        )
        return {
            "fiscal_year_id": fiscal_year.id,
            "revenue": str(revenue),
            "expense": str(expense),
            "net_profit": str(net_profit),
            "journal_entry_id": entries[0].id if entries else None,
            "closed_periods": len(open_periods),
        }

    def _context(self, fiscal_year: FiscalYear):
        from app.services.posting_service import DocumentPostingContext

        return DocumentPostingContext(
            document_type="period_close",
            document_id=fiscal_year.id,
            document_no=f"CLOSE-{fiscal_year.code}",
            document_date=fiscal_year.end_date,
            description=f"Year end close {fiscal_year.code}",
        )


class PostingRuleService:
    """CRUD-ish helpers for the configurable posting rules."""

    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id

    def ensure_default_rules(self) -> int:
        """Seed the standard posting rules from the chart defaults."""
        created = 0
        defaults = [
            # document_type, line_role, account_source, side, amount_source
            ("sales_invoice", "ar", "system.1210", "debit", "document_total"),
            ("sales_invoice", "sales_revenue", "system.4110", "credit", "line_net"),
            ("sales_invoice", "tax_payable", "system.2210", "credit", "line_tax"),
            ("sales_invoice", "discount", "system.4120", "debit", "line_discount"),
            ("sales_invoice", "cogs", "system.5110", "debit", "line_cost"),
            ("sales_invoice", "inventory", "system.1310", "credit", "line_cost"),
            ("sales_invoice", "shipping_revenue", "system.4130", "credit", "document_charges"),
            ("delivery_note", "cogs", "system.5110", "debit", "line_cost"),
            ("delivery_note", "inventory", "system.1310", "credit", "line_cost"),
            ("credit_note", "ar", "system.1210", "credit", "document_total"),
            ("credit_note", "sales_revenue", "system.4110", "debit", "line_net"),
            ("credit_note", "tax_payable", "system.2210", "debit", "line_tax"),
            ("credit_note", "cogs", "system.5110", "credit", "line_cost"),
            ("credit_note", "inventory", "system.1310", "debit", "line_cost"),
            ("goods_receipt", "inventory", "system.1310", "debit", "line_cost"),
            ("goods_receipt", "grni", "system.2130", "credit", "line_cost"),
            ("purchase_invoice", "ap", "system.2110", "credit", "document_total"),
            ("purchase_invoice", "grni", "system.2130", "debit", "line_received"),
            ("purchase_invoice", "inventory", "system.1310", "debit", "line_net"),
            ("purchase_invoice", "purchase_expense", "system.5130", "debit", "line_net"),
            ("purchase_invoice", "tax_receivable", "system.1410", "debit", "line_tax"),
            ("purchase_invoice", "purchase_discount", "system.5140", "credit", "line_discount"),
            ("purchase_invoice", "withholding_tax", "system.2220", "debit", "document_withholding"),
            ("debit_note", "ap", "system.2110", "debit", "document_total"),
            ("debit_note", "inventory", "system.1310", "credit", "line_net"),
            ("debit_note", "purchase_expense", "system.5130", "credit", "line_net"),
            ("debit_note", "tax_receivable", "system.1410", "credit", "line_tax"),
            ("payment", "ar", "system.1210", "credit", "document_total"),
            ("payment", "ap", "system.2110", "debit", "document_total"),
            ("payment", "withholding_tax", "system.2220", "credit", "document_withholding"),
            ("treasury_transfer", "bank_charges", "system.5210", "debit", "document_charges"),
            ("stock_adjustment", "inventory", "system.1310", "auto", "line_cost"),
            ("stock_adjustment", "inventory_adjustment", "system.5160", "auto", "line_cost"),
            ("production_order", "wip", "system.1320", "debit", "line_cost"),
            ("production_order", "inventory", "system.1310", "credit", "line_cost"),
            ("production_order", "manufacturing_overhead", "system.5180", "debit", "line_cost"),
            ("asset_depreciation", "depreciation_expense", "system.6120", "debit", "line_cost"),
            ("asset_depreciation", "accumulated_depreciation", "system.1330", "credit", "line_cost"),
            ("payroll_run", "salary_expense", "system.6110", "debit", "document_gross"),
            ("payroll_run", "salary_payable", "system.2230", "credit", "document_net"),
            ("payroll_run", "payroll_tax", "system.2240", "credit", "document_tax"),
            ("payroll_run", "social_insurance", "system.2250", "credit", "document_insurance"),
            ("expense", "expense_account", "system.5130", "debit", "document_subtotal"),
            ("expense", "ap", "system.2110", "credit", "document_total"),
            ("expense", "tax_receivable", "system.1410", "debit", "document_tax"),
            ("period_close", "retained_earnings", "system.3110", "auto", "document_total"),
        ]
        for index, (document_type, role, source, side, amount_source) in enumerate(defaults, start=10):
            existing = self.db.execute(
                select(PostingRule).where(
                    PostingRule.company_id == self.company_id,
                    PostingRule.document_type == document_type,
                    PostingRule.line_role == role,
                )
            ).scalars().first()
            if existing is not None:
                continue
            self.db.add(
                PostingRule(
                    company_id=self.company_id,
                    name=f"{document_type} :: {role}",
                    document_type=document_type,
                    line_role=role,
                    account_source=source,
                    entry_side=side,
                    amount_source=amount_source,
                    sequence_no=index,
                )
            )
            created += 1
        self.db.flush()
        return created
