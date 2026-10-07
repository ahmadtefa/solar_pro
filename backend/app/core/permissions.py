"""Permission catalogue and role templates.

Permissions are addressed as ``<module>.<entity>.<action>``.  The catalogue is
declared as data so a new module/entity automatically becomes grantable without
touching the authorization code.
"""

from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatch

# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
VIEW = "view"
CREATE = "create"
EDIT = "edit"
DELETE = "delete"
SUBMIT = "submit"
APPROVE = "approve"
REJECT = "reject"
CANCEL = "cancel"
POST = "post"
UNPOST = "unpost"
PRINT = "print"
EXPORT = "export"
IMPORT = "import"
CLOSE = "close"
RECONCILE = "reconcile"
PAY = "pay"
ISSUE = "issue"
ASSIGN = "assign"
EXECUTE = "execute"

MASTER_ACTIONS: tuple[str, ...] = (VIEW, CREATE, EDIT, DELETE, IMPORT, EXPORT, PRINT)
DOCUMENT_ACTIONS: tuple[str, ...] = (
    VIEW, CREATE, EDIT, DELETE, SUBMIT, APPROVE, REJECT, CANCEL, POST, UNPOST, PRINT, EXPORT,
)
REPORT_ACTIONS: tuple[str, ...] = (VIEW, EXPORT, PRINT)

# --------------------------------------------------------------------------- #
# Catalogue: module -> {entity: actions}
# --------------------------------------------------------------------------- #
CATALOGUE: dict[str, dict[str, tuple[str, ...]]] = {
    "core": {
        "company": MASTER_ACTIONS,
        "branch": MASTER_ACTIONS,
        "department": MASTER_ACTIONS,
        "division": MASTER_ACTIONS,
        "cost_center": MASTER_ACTIONS,
        "fiscal_year": (VIEW, CREATE, EDIT, DELETE, CLOSE, EXPORT),
        "fiscal_period": (VIEW, CREATE, EDIT, CLOSE),
        "currency": MASTER_ACTIONS,
        "exchange_rate": MASTER_ACTIONS,
        "tax": MASTER_ACTIONS,
        "payment_term": MASTER_ACTIONS,
        "unit": MASTER_ACTIONS,
        "unit_group": MASTER_ACTIONS,
        "unit_conversion": MASTER_ACTIONS,
        "number_sequence": (VIEW, CREATE, EDIT, DELETE),
        "document_type": MASTER_ACTIONS,
        "system_setting": (VIEW, EDIT, EXPORT),
        "module": (VIEW, EDIT),
        "country": MASTER_ACTIONS,
        "city": MASTER_ACTIONS,
        "address": MASTER_ACTIONS,
        "user": (VIEW, CREATE, EDIT, DELETE, EXPORT),
        "role": (VIEW, CREATE, EDIT, DELETE, EXPORT),
        "permission": (VIEW, EXPORT),
        "session": (VIEW, DELETE),
        "audit_log": (VIEW, EXPORT),
        "notification": (VIEW, EDIT, DELETE),
        "attachment": (VIEW, CREATE, EDIT, DELETE, PRINT, EXPORT),
        "backup": (VIEW, CREATE, EXECUTE, DELETE, EXPORT),
        "report": REPORT_ACTIONS,
        "saved_report": (VIEW, CREATE, EDIT, DELETE, EXPORT),
        "dashboard": (VIEW, EXPORT),
        "search": (VIEW,),
        "import_job": (VIEW, CREATE, EXECUTE, EXPORT, PRINT),
    },
    "crm": {
        "lead": MASTER_ACTIONS,
        "lead_source": MASTER_ACTIONS,
        "pipeline_stage": MASTER_ACTIONS,
        "opportunity": MASTER_ACTIONS,
        "activity": MASTER_ACTIONS,
        "customer": MASTER_ACTIONS,
        "customer_group": MASTER_ACTIONS,
        "contact": MASTER_ACTIONS,
        "sales_target": MASTER_ACTIONS,
    },
    "suppliers": {
        "supplier": MASTER_ACTIONS,
        "supplier_group": MASTER_ACTIONS,
        "supplier_product": MASTER_ACTIONS,
        "supplier_price": (VIEW, CREATE, EXPORT),
        "supplier_evaluation": MASTER_ACTIONS,
    },
    "inventory": {
        "product": MASTER_ACTIONS,
        "product_category": MASTER_ACTIONS,
        "brand": MASTER_ACTIONS,
        "product_unit": MASTER_ACTIONS,
        "product_barcode": MASTER_ACTIONS,
        "price_list": MASTER_ACTIONS,
        "warehouse": MASTER_ACTIONS,
        "warehouse_zone": MASTER_ACTIONS,
        "warehouse_location": MASTER_ACTIONS,
        "batch": MASTER_ACTIONS,
        "serial": MASTER_ACTIONS,
        "stock_ledger": (VIEW, EXPORT, PRINT),
        "stock_balance": (VIEW, EXPORT, PRINT),
        "stock_transfer": DOCUMENT_ACTIONS,
        "stock_adjustment": DOCUMENT_ACTIONS,
        "stock_count": DOCUMENT_ACTIONS,
        "reorder_rule": MASTER_ACTIONS,
        "inventory_valuation": (VIEW, EXPORT),
    },
    "purchasing": {
        "purchase_request": DOCUMENT_ACTIONS,
        "rfq": DOCUMENT_ACTIONS,
        "supplier_quotation": DOCUMENT_ACTIONS,
        "purchase_order": DOCUMENT_ACTIONS,
        "goods_receipt": DOCUMENT_ACTIONS,
        "purchase_invoice": DOCUMENT_ACTIONS,
        "debit_note": DOCUMENT_ACTIONS,
    },
    "sales": {
        "quotation": DOCUMENT_ACTIONS,
        "sales_order": DOCUMENT_ACTIONS,
        "delivery_note": DOCUMENT_ACTIONS,
        "sales_invoice": DOCUMENT_ACTIONS,
        "credit_note": DOCUMENT_ACTIONS,
        "sales_commission": (VIEW, CREATE, EDIT, APPROVE, PAY, EXPORT),
        "pos_terminal": MASTER_ACTIONS,
        "pos_shift": (VIEW, CREATE, EDIT, CLOSE, RECONCILE, EXPORT, PRINT),
        "pos_sale": (VIEW, CREATE, PRINT, EXPORT, CANCEL),
    },
    "accounting": {
        "account": MASTER_ACTIONS,
        "journal_entry": DOCUMENT_ACTIONS,
        "general_ledger": REPORT_ACTIONS,
        "trial_balance": REPORT_ACTIONS,
        "balance_sheet": REPORT_ACTIONS,
        "income_statement": REPORT_ACTIONS,
        "cash_flow": REPORT_ACTIONS,
        "customer_ledger": REPORT_ACTIONS,
        "supplier_ledger": REPORT_ACTIONS,
        "posting_rule": MASTER_ACTIONS,
        "period_close": (VIEW, EXECUTE, CLOSE),
        "ageing": REPORT_ACTIONS,
    },
    "treasury": {
        "cash_account": MASTER_ACTIONS,
        "bank_account": MASTER_ACTIONS,
        "payment": DOCUMENT_ACTIONS,
        "receipt": DOCUMENT_ACTIONS,
        "treasury_transfer": DOCUMENT_ACTIONS,
        "cheque": MASTER_ACTIONS,
        "bank_reconciliation": (VIEW, CREATE, EDIT, RECONCILE, DELETE, EXPORT, PRINT),
        "cash_flow": REPORT_ACTIONS,
        "currency_revaluation": DOCUMENT_ACTIONS,
    },
    "assets": {
        "asset_category": MASTER_ACTIONS,
        "asset": MASTER_ACTIONS,
        "depreciation": (VIEW, CREATE, EXECUTE, POST, UNPOST, EXPORT, PRINT),
        "asset_transfer": DOCUMENT_ACTIONS,
        "asset_disposal": DOCUMENT_ACTIONS,
        "asset_maintenance": DOCUMENT_ACTIONS,
    },
    "expenses": {
        "expense_category": MASTER_ACTIONS,
        "expense": DOCUMENT_ACTIONS,
        "expense_claim": DOCUMENT_ACTIONS,
        "expense_advance": DOCUMENT_ACTIONS,
        "budget": (VIEW, CREATE, EDIT, DELETE, APPROVE, EXPORT, PRINT),
    },
    "hr": {
        "employee": MASTER_ACTIONS,
        "employee_contract": MASTER_ACTIONS,
        "position": MASTER_ACTIONS,
        "attendance": (VIEW, CREATE, EDIT, DELETE, APPROVE, IMPORT, EXPORT, PRINT),
        "shift": MASTER_ACTIONS,
        "leave_type": MASTER_ACTIONS,
        "leave_request": DOCUMENT_ACTIONS,
        "leave_balance": (VIEW, CREATE, EDIT, EXPORT),
        "holiday": MASTER_ACTIONS,
        "payroll_period": MASTER_ACTIONS,
        "payroll_run": DOCUMENT_ACTIONS + (EXECUTE, PAY),
        "payslip": (VIEW, PRINT, EXPORT),
        "loan": (VIEW, CREATE, EDIT, DELETE, APPROVE, PAY),
    },
    "manufacturing": {
        "work_center": MASTER_ACTIONS,
        "bom": MASTER_ACTIONS,
        "routing": MASTER_ACTIONS,
        "production_order": DOCUMENT_ACTIONS + (EXECUTE, ISSUE,),
        "production_output": (VIEW, CREATE, POST, PRINT),
        "scrap": (VIEW, CREATE, DELETE, EXPORT),
    },
    "projects": {
        "project": MASTER_ACTIONS,
        "project_phase": MASTER_ACTIONS,
        "task": MASTER_ACTIONS,
        "milestone": MASTER_ACTIONS,
        "timesheet": DOCUMENT_ACTIONS,
        "project_resource": MASTER_ACTIONS,
        "project_billing": (VIEW, CREATE, EDIT, APPROVE, EXPORT),
        "profitability": REPORT_ACTIONS,
    },
    "service": {
        "service_request": DOCUMENT_ACTIONS + (ASSIGN,),
        "ticket": DOCUMENT_ACTIONS + (ASSIGN,),
        "work_order": DOCUMENT_ACTIONS + (ASSIGN, EXECUTE),
        "service_contract": DOCUMENT_ACTIONS,
        "warranty": MASTER_ACTIONS,
        "technician_schedule": MASTER_ACTIONS,
    },
    "workflow": {
        "workflow_definition": MASTER_ACTIONS,
        "workflow_instance": (VIEW, CREATE, CANCEL, EXPORT),
        "approval": (VIEW, APPROVE, REJECT, EXPORT),
        "delegation": MASTER_ACTIONS,
    },
    "reports": {
        "report": REPORT_ACTIONS,
        "sales_report": REPORT_ACTIONS,
        "purchase_report": REPORT_ACTIONS,
        "inventory_report": REPORT_ACTIONS,
        "financial_report": REPORT_ACTIONS,
        "hr_report": REPORT_ACTIONS,
        "project_report": REPORT_ACTIONS,
        "tax_report": REPORT_ACTIONS,
    },
}

ALL_ACTIONS: tuple[str, ...] = tuple(
    sorted({action for entities in CATALOGUE.values() for actions in entities.values() for action in actions})
)


def iter_permissions() -> Iterable[tuple[str, str, str, str]]:
    """Yield ``(code, module, entity, action)`` for the whole catalogue."""
    for module, entities in CATALOGUE.items():
        for entity, actions in entities.items():
            for action in actions:
                yield f"{module}.{entity}.{action}", module, entity, action


def all_permission_codes() -> list[str]:
    return [code for code, *_ in iter_permissions()]


def entity_permission_templates() -> dict[str, list[str]]:
    """Map ``module.entity`` to its action list (used by the UI permission picker)."""
    return {f"{module}.{entity}": list(actions) for module, entities in CATALOGUE.items() for entity, actions in entities.items()}


# --------------------------------------------------------------------------- #
# Role templates used by the seeder and by "new company" bootstrap
# --------------------------------------------------------------------------- #
_ROLE_PATTERNS: dict[str, dict[str, object]] = {
    "company_admin": {
        "name": "Company Administrator",
        "name_ar": "مدير الشركة",
        "data_scope": "all_branches",
        "level": 1,
        "patterns": ["*"],
    },
    "general_manager": {
        "name": "General Manager",
        "name_ar": "المدير العام",
        "data_scope": "all_branches",
        "level": 2,
        "patterns": [
            "*.*.view", "*.*.export", "*.*.print", "*.*.approve", "*.*.reject",
            "sales.*.create", "sales.*.edit", "purchasing.*.create", "purchasing.*.edit",
        ],
    },
    "branch_manager": {
        "name": "Branch Manager",
        "name_ar": "مدير الفرع",
        "data_scope": "specific_branches",
        "level": 3,
        "patterns": [
            "*.*.view", "*.*.print", "*.*.export", "*.*.approve", "*.*.reject",
            "sales.*.*", "purchasing.*.*", "inventory.*.*", "crm.*.*", "service.*.*", "projects.*.*",
            "treasury.payment.view", "treasury.receipt.view", "accounting.*.view",
        ],
    },
    "sales_manager": {
        "name": "Sales Manager",
        "name_ar": "مدير المبيعات",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": [
            "crm.*.*", "sales.*.*", "inventory.product.view", "inventory.stock_balance.view",
            "inventory.price_list.*", "reporting.*", "reports.*", "core.*.view", "workflow.approval.*",
        ],
    },
    "sales_rep": {
        "name": "Sales Representative",
        "name_ar": "مندوب مبيعات",
        "data_scope": "own_records",
        "level": 6,
        "patterns": [
            "crm.lead.*", "crm.opportunity.*", "crm.activity.*", "crm.customer.view", "crm.customer.create",
            "crm.customer.edit", "crm.contact.*", "sales.quotation.*", "sales.sales_order.*",
            "sales.sales_invoice.view", "sales.sales_invoice.print", "inventory.product.view",
            "inventory.stock_balance.view", "reports.sales_report.view",
        ],
    },
    "accountant": {
        "name": "Accountant",
        "name_ar": "محاسب",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": [
            "accounting.*.*", "treasury.*.*", "expenses.*.*", "assets.*.*", "sales.sales_invoice.view",
            "sales.sales_invoice.post", "sales.sales_invoice.unpost", "sales.credit_note.view",
            "purchasing.purchase_invoice.*", "purchasing.debit_note.*", "hr.payroll_run.*", "core.*.view",
            "core.tax.*", "core.exchange_rate.*", "reports.*", "workflow.approval.*",
        ],
    },
    "warehouse_manager": {
        "name": "Warehouse Manager",
        "name_ar": "مدير المستودع",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": [
            "inventory.*.*", "sales.delivery_note.*", "purchasing.goods_receipt.*",
            "purchasing.purchase_request.*", "purchasing.purchase_order.view", "reports.inventory_report.*",
            "core.*.view", "manufacturing.production_order.view", "manufacturing.production_order.issue",
            "service.work_order.view",
        ],
    },
    "warehouse_clerk": {
        "name": "Warehouse Clerk",
        "name_ar": "أمين مستودع",
        "data_scope": "specific_branches",
        "level": 7,
        "patterns": [
            "inventory.stock_balance.view", "inventory.stock_ledger.view", "inventory.stock_transfer.*",
            "inventory.stock_count.*", "inventory.stock_adjustment.create", "inventory.stock_adjustment.view",
            "inventory.product.view", "inventory.batch.*", "inventory.serial.*",
            "purchasing.goods_receipt.view", "sales.delivery_note.view", "sales.delivery_note.create",
            "sales.delivery_note.edit",
        ],
    },
    "purchasing_manager": {
        "name": "Purchasing Manager",
        "name_ar": "مدير المشتريات",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": [
            "purchasing.*.*", "suppliers.*.*", "inventory.product.view", "inventory.stock_balance.view",
            "inventory.reorder_rule.*", "expenses.expense.view", "expenses.expense.approve",
            "reports.purchase_report.*", "core.*.view", "workflow.approval.*",
        ],
    },
    "hr_manager": {
        "name": "HR Manager",
        "name_ar": "مدير الموارد البشرية",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": ["hr.*.*", "core.user.*", "core.role.view", "reports.hr_report.*", "core.*.view", "workflow.approval.*"],
    },
    "service_manager": {
        "name": "Service Manager",
        "name_ar": "مدير الصيانة",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": ["service.*.*", "projects.*.*", "sales.sales_order.view", "sales.sales_invoice.view",
                     "inventory.product.view", "inventory.stock_balance.view", "crm.customer.view",
                     "assets.asset.*", "reports.service_report.*", "reports.project_report.*", "workflow.approval.*"],
    },
    "project_manager": {
        "name": "Project Manager",
        "name_ar": "مدير المشاريع",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": ["projects.*.*", "service.work_order.*", "inventory.product.view", "inventory.stock_balance.view",
                     "purchasing.purchase_request.*", "expenses.expense.*", "reports.project_report.*",
                     "hr.timesheet.view", "crm.customer.view", "workflow.approval.*"],
    },
    "manufacturing_manager": {
        "name": "Production Manager",
        "name_ar": "مدير الإنتاج",
        "data_scope": "all_branches",
        "level": 4,
        "patterns": ["manufacturing.*.*", "inventory.*.view", "inventory.stock_transfer.*",
                     "inventory.stock_adjustment.view", "purchasing.purchase_request.*", "reports.inventory_report.*"],
    },
    "pos_cashier": {
        "name": "POS Cashier",
        "name_ar": "كاشير",
        "data_scope": "specific_branches",
        "level": 8,
        "patterns": [
            "sales.pos_terminal.view", "sales.pos_shift.*", "sales.pos_sale.*", "sales.sales_invoice.create",
            "sales.sales_invoice.view",
            "sales.sales_invoice.print", "sales.sales_invoice.post", "inventory.product.view",
            "inventory.stock_balance.view", "treasury.cash_account.view",
        ],
    },
    "auditor": {
        "name": "Auditor",
        "name_ar": "مراجع",
        "data_scope": "all_branches",
        "level": 5,
        "patterns": ["*.*.view", "*.*.export", "*.*.print", "core.audit_log.*", "accounting.*.view"],
    },
    "viewer": {
        "name": "Read Only",
        "name_ar": "قراءة فقط",
        "data_scope": "all_branches",
        "level": 9,
        "patterns": ["*.*.view", "*.*.print"],
    },
}

ROLE_TEMPLATES = _ROLE_PATTERNS


def expand_patterns(patterns: Iterable[str], catalogue: Iterable[str] | None = None) -> set[str]:
    """Expand wildcard patterns (``sales.*.view``) against the catalogue."""
    codes = list(catalogue) if catalogue is not None else all_permission_codes()
    if "*" in patterns:  # pragma: no cover - handled below but keeps intent explicit
        return set(codes)
    resolved: set[str] = set()
    for pattern in patterns:
        if pattern == "*":
            return set(codes)
        for code in codes:
            if fnmatch(code, pattern):
                resolved.add(code)
    return resolved


def expand_role_template(template_key: str, catalogue: Iterable[str] | None = None) -> tuple[dict, set[str]]:
    template = ROLE_TEMPLATES[template_key]
    return template, expand_patterns(template["patterns"], catalogue)  # type: ignore[arg-type]


class PermissionSet:
    """In-memory permission set with wildcard support for a user in a company."""

    __slots__ = ("codes", "_wildcards")

    def __init__(self, codes: Iterable[str]) -> None:
        self.codes = {code.strip() for code in codes if code}
        self._wildcards = {code for code in self.codes if "*" in code}

    def __contains__(self, code: str) -> bool:
        return self.has(code)

    def has(self, code: str) -> bool:
        if not code:
            return False
        if code in self.codes:
            return True
        for pattern in self._wildcards:
            if fnmatch(code, pattern):
                return True
        return False

    def any_of(self, *codes: str) -> bool:
        return any(self.has(code) for code in codes)

    def all_of(self, *codes: str) -> bool:
        return all(self.has(code) for code in codes)

    def as_sorted_list(self) -> list[str]:
        return sorted(self.codes)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.codes)
