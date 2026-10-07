"""Company provisioning, module activation and demo seeding.

Everything here is data driven: a company can be provisioned with its own
currency, chart of accounts, tax configuration and numbering rules without any
country specific logic in the code base.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import set_session_tenant
from app.core.enums import ModuleKey, TaxComputation, TaxInclusion, TaxType, ValuationMethod
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.core.permissions import CATALOGUE, ROLE_TEMPLATES, all_permission_codes, expand_role_template
from app.core.security import hash_password
from app.models.accounting import Account
from app.models.identity import (
    Permission,
    Role,
    RolePermission,
    User,
    UserBranchAccess,
    UserCompanyAccess,
    UserRole,
    UserWarehouseAccess,
)
from app.models.masterdata import Warehouse, WarehouseLocation
from app.models.platform import (
    Branch,
    Company,
    Country,
    Currency,
    Department,
    DocumentType,
    FiscalYear,
    ModuleActivation,
    PaymentTerm,
    SystemSetting,
    Tax,
    UnitGroup,
    UnitOfMeasure,
)
from app.services.accounting_service import ChartOfAccountsService, FiscalCalendarService, PostingRuleService
from app.services.numbering_service import DEFAULT_PREFIXES, NumberingService

DOCUMENT_TYPE_NAMES: dict[str, str] = {
    "quotation": "Sales Quotation",
    "sales_order": "Sales Order",
    "delivery_note": "Delivery Note",
    "sales_invoice": "Sales Invoice",
    "credit_note": "Credit Note",
    "pos_invoice": "POS Invoice",
    "pos_shift": "POS Shift",
    "purchase_request": "Purchase Request",
    "rfq": "Request for Quotation",
    "supplier_quotation": "Supplier Quotation",
    "purchase_order": "Purchase Order",
    "goods_receipt": "Goods Receipt",
    "purchase_invoice": "Purchase Invoice",
    "debit_note": "Debit Note",
    "journal_entry": "Journal Entry",
    "payment": "Payment",
    "receipt": "Receipt",
    "treasury_transfer": "Treasury Transfer",
    "bank_reconciliation": "Bank Reconciliation",
    "stock_adjustment": "Stock Adjustment",
    "stock_transfer": "Stock Transfer",
    "stocktake": "Stocktake",
    "production_order": "Production Order",
    "asset": "Fixed Asset",
    "expense": "Expense",
    "expense_claim": "Expense Claim",
    "payroll_run": "Payroll Run",
    "project": "Project",
    "work_order": "Work Order",
    "ticket": "Service Ticket",
    "service_contract": "Service Contract",
}

DEFAULT_UNITS: list[dict[str, Any]] = [
    {"code": "PCS", "name": "Piece", "name_ar": "قطعة", "is_base": True, "decimals": 0},
    {"code": "BOX", "name": "Box", "name_ar": "علبة", "is_base": False, "decimals": 0},
    {"code": "KG", "name": "Kilogram", "name_ar": "كيلوجرام", "is_base": True, "decimals": 3},
    {"code": "GM", "name": "Gram", "name_ar": "جرام", "is_base": False, "decimals": 0},
    {"code": "LTR", "name": "Litre", "name_ar": "لتر", "is_base": True, "decimals": 3},
    {"code": "MTR", "name": "Meter", "name_ar": "متر", "is_base": True, "decimals": 2},
    {"code": "SQM", "name": "Square Meter", "name_ar": "متر مربع", "is_base": True, "decimals": 2},
    {"code": "HR", "name": "Hour", "name_ar": "ساعة", "is_base": True, "decimals": 2},
    {"code": "DAY", "name": "Day", "name_ar": "يوم", "is_base": True, "decimals": 0},
    {"code": "SET", "name": "Set", "name_ar": "طقم", "is_base": True, "decimals": 0},
]

DEFAULT_ACTIVE_MODULES = [module.value for module in ModuleKey]

DEFAULT_SETTINGS: dict[str, Any] = {
    "invoice.footer_note": "",
    "invoice.show_tax_number": True,
    "sales.allow_negative_stock": False,
    "sales.default_credit_days": 30,
    "inventory.valuation_method": ValuationMethod.AVERAGE.value,
    "inventory.low_stock_alerts": True,
    "accounting.auto_post_invoices": True,
    "pos.receipt_header": "",
    "pos.cash_variance_tolerance": "0",
    "numbering.reset_yearly": True,
    "notifications.channels": ["in_app", "email"],
}


class BootstrapService:
    """Creates a fully usable company from a small JSON payload."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------- currencies
    def ensure_currency(self, code: str, name: str | None = None, symbol: str | None = None, decimals: int = 2) -> Currency:
        code = code.upper()
        currency = self.db.execute(select(Currency).where(Currency.code == code)).scalars().first()
        if currency is not None:
            return currency
        currency = Currency(code=code, name=name or code, symbol=symbol or code, decimal_places=decimals)
        self.db.add(currency)
        self.db.flush()
        return currency

    def ensure_units(self, company_id: uuid.UUID) -> dict[str, UnitOfMeasure]:
        group = self.db.execute(
            select(UnitGroup).where(UnitGroup.company_id == company_id, UnitGroup.code == "GENERAL")
        ).scalars().first()
        if group is None:
            group = UnitGroup(company_id=company_id, code="GENERAL", name="General", name_ar="عام")
            self.db.add(group)
            self.db.flush()
        units: dict[str, UnitOfMeasure] = {}
        for item in DEFAULT_UNITS:
            unit = self.db.execute(
                select(UnitOfMeasure).where(
                    UnitOfMeasure.company_id == company_id, UnitOfMeasure.code == item["code"]
                )
            ).scalars().first()
            if unit is None:
                unit = UnitOfMeasure(
                    company_id=company_id,
                    code=item["code"],
                    name=item["name"],
                    name_ar=item.get("name_ar"),
                    unit_group_id=group.id,
                    allow_fraction=bool(item.get("decimals", 0)),
                    is_base=bool(item.get("is_base", False)),
                )
                self.db.add(unit)
                self.db.flush()
            units[item["code"]] = unit
        return units

    def ensure_roles(self, company_id: uuid.UUID) -> dict[str, Role]:
        catalogue = all_permission_codes()
        existing_permissions = {code for (code,) in self.db.execute(select(Permission.code)).all()}
        for module, entities in CATALOGUE.items():
            for entity, actions in entities.items():
                for action in actions:
                    code = f"{module}.{entity}.{action}"
                    if code in existing_permissions:
                        continue
                    self.db.add(
                        Permission(
                            code=code,
                            module=module,
                            entity=entity,
                            action=action,
                            description=f"{action.title()} {entity.replace('_', ' ')}",
                            is_system=True,
                        )
                    )
                    existing_permissions.add(code)
        self.db.flush()

        permission_ids = {code: pid for pid, code in self.db.execute(select(Permission.id, Permission.code)).all()}

        roles: dict[str, Role] = {}
        for key, template in ROLE_TEMPLATES.items():
            role = self.db.execute(
                select(Role).where(Role.company_id == company_id, Role.code == key)
            ).scalars().first()
            if role is None:
                role = Role(
                    company_id=company_id,
                    code=key,
                    name=str(template["name"]),
                    name_ar=str(template.get("name_ar") or ""),
                    description=f"Built-in role template: {key}",
                    data_scope=str(template.get("data_scope", "all_branches")),
                    level=int(template.get("level", 10)),
                    is_system=True,
                )
                self.db.add(role)
                self.db.flush()
            assigned = {
                permission_id
                for (permission_id,) in self.db.execute(
                    select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                ).all()
            }
            for code in expand_role_template(key, catalogue)[1]:
                permission_id = permission_ids.get(code)
                if permission_id is None or permission_id in assigned:
                    continue
                self.db.add(RolePermission(role_id=role.id, permission_id=permission_id))
                assigned.add(permission_id)
            roles[key] = role
        self.db.flush()
        return roles

    # -------------------------------------------------------------- chart/GAAP
    def ensure_chart_of_accounts(self, company_id: uuid.UUID) -> dict[str, uuid.UUID]:
        return ChartOfAccountsService(self.db, company_id).create_standard_chart()

    def ensure_numbering(self, company_id: uuid.UUID, *, branch_id: uuid.UUID | None = None) -> None:
        numbering = NumberingService(self.db, company_id)
        for document_type, prefix in DEFAULT_PREFIXES.items():
            numbering.configure(document_type, prefix=prefix, branch_id=branch_id)

    def ensure_document_types(self, company_id: uuid.UUID) -> None:
        for document_type, name in DOCUMENT_TYPE_NAMES.items():
            existing = self.db.execute(
                select(DocumentType).where(
                    DocumentType.company_id == company_id, DocumentType.code == document_type
                )
            ).scalars().first()
            if existing is not None:
                continue
            self.db.add(
                DocumentType(
                    company_id=company_id,
                    code=document_type,
                    name=name,
                    module=document_type.split("_")[0],
                    requires_approval=document_type
                    not in {"quotation", "sales_order", "delivery_note", "journal_entry", "pos_invoice", "pos_shift"},
                    affects_inventory=document_type
                    in {
                        "delivery_note",
                        "goods_receipt",
                        "stock_adjustment",
                        "stock_transfer",
                        "stocktake",
                        "production_order",
                        "pos_invoice",
                        "credit_note",
                        "debit_note",
                    },
                    affects_accounting=document_type
                    not in {"quotation", "rfq", "supplier_quotation", "purchase_request", "pos_shift"},
                )
            )
        self.db.flush()

    def ensure_settings(self, company_id: uuid.UUID, overrides: dict[str, Any] | None = None) -> None:
        values = {**DEFAULT_SETTINGS, **(overrides or {})}
        for key, value in values.items():
            existing = self.db.execute(
                select(SystemSetting).where(SystemSetting.company_id == company_id, SystemSetting.key == key)
            ).scalars().first()
            if existing is not None:
                continue
            self.db.add(
                SystemSetting(
                    company_id=company_id,
                    key=key,
                    value=str(value) if not isinstance(value, (dict, list)) else None,
                    value_json=value if isinstance(value, (dict, list)) else None,
                    category=key.split(".")[0],
                    scope="company",
                )
            )
        self.db.flush()

    def ensure_modules(self, company_id: uuid.UUID, modules: Iterable[str] | None = None) -> None:
        for module_key in modules or DEFAULT_ACTIVE_MODULES:
            existing = self.db.execute(
                select(ModuleActivation).where(
                    ModuleActivation.company_id == company_id, ModuleActivation.module_key == module_key
                )
            ).scalars().first()
            if existing is not None:
                continue
            self.db.add(ModuleActivation(company_id=company_id, module_key=module_key, is_enabled=True))
        self.db.flush()

    # ---------------------------------------------------------------- company
    def create_company(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = str(payload["code"]).strip().upper()
        existing = self.db.execute(select(Company).where(Company.code == code)).scalars().first()
        if existing is not None:
            raise ConflictError(f"A company with code {code} already exists")
        base_currency = str(payload.get("base_currency_code") or settings.default_currency_code).upper()
        self.ensure_currency(base_currency, payload.get("currency_name"))
        country_code = str(payload.get("country_code") or settings.default_country_code).upper()
        self.ensure_country(country_code, payload.get("country_name"), base_currency, payload.get("phone_code"))

        company = Company(
            code=code,
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            legal_name=payload.get("legal_name"),
            tax_registration_number=payload.get("tax_registration_number"),
            commercial_registry=payload.get("commercial_registry"),
            industry=payload.get("industry"),
            base_currency_code=base_currency,
            country_code=country_code,
            timezone=payload.get("timezone") or settings.default_timezone,
            default_language=payload.get("default_language", "ar"),
            phone=payload.get("phone"),
            email=payload.get("email"),
            website=payload.get("website"),
            fiscal_year_start_month=int(payload.get("fiscal_year_start_month") or settings.fiscal_year_start_month),
            valuation_method=str(payload.get("valuation_method") or ValuationMethod.AVERAGE.value),
            is_active=True,
            settings_json=payload.get("settings_json") or {},
        )
        self.db.add(company)
        self.db.flush()
        set_session_tenant(self.db, company.id)

        self.ensure_modules(company.id, payload.get("modules"))
        self.ensure_chart_of_accounts(company.id)
        self.ensure_roles(company.id)
        self.ensure_document_types(company.id)
        self.ensure_settings(company.id, payload.get("settings"))
        PostingRuleService(self.db, company.id).ensure_default_rules()
        units = self.ensure_units(company.id)

        branch = self._create_branch(company, payload.get("branch") or {})
        department = self._create_department(company, branch, {"code": "ADMIN", "name": "Administration", "name_ar": "الإدارة"})
        warehouse = self._create_warehouse(company, branch, payload.get("warehouse") or {})
        self.ensure_numbering(company.id, branch_id=branch.id)

        fiscal_year = self._create_fiscal_year(company, payload.get("fiscal_year") or {})
        payment_terms = self._create_payment_terms(company)
        taxes = self._create_taxes(company, payload.get("taxes") or [], chart_owner=self)

        return {
            "company": company,
            "branch": branch,
            "department": department,
            "warehouse": warehouse,
            "fiscal_year": fiscal_year,
            "units": units,
            "payment_terms": payment_terms,
            "taxes": taxes,
            "settings": DEFAULT_SETTINGS,
        }

    def ensure_country(
        self, code: str, name: str | None = None, currency_code: str | None = None, phone_code: str | None = None
    ) -> Country:
        country = self.db.execute(select(Country).where(Country.code == code)).scalars().first()
        if country is not None:
            return country
        country = Country(code=code, name=name or code, default_currency_code=currency_code, phone_code=phone_code)
        self.db.add(country)
        self.db.flush()
        return country

    def _create_branch(self, company: Company, payload: dict[str, Any]) -> Branch:
        branch = Branch(
            company_id=company.id,
            code=str(payload.get("code") or "MAIN"),
            name=str(payload.get("name") or "Main Branch"),
            name_ar=payload.get("name_ar") or "الفرع الرئيسي",
            country_code=company.country_code,
            address_line1=payload.get("address_line1"),
            phone=payload.get("phone"),
            email=payload.get("email"),
            is_head_office=bool(payload.get("is_head_office", True)),
            is_active=True,
        )
        self.db.add(branch)
        self.db.flush()
        return branch

    def _create_department(self, company: Company, branch: Branch, payload: dict[str, Any]) -> Department:
        department = Department(
            company_id=company.id,
            branch_id=branch.id,
            code=str(payload.get("code") or "GEN"),
            name=str(payload.get("name") or "General"),
            name_ar=payload.get("name_ar"),
        )
        self.db.add(department)
        self.db.flush()
        return department

    def _create_warehouse(self, company: Company, branch: Branch, payload: dict[str, Any]) -> Warehouse:
        warehouse = Warehouse(
            company_id=company.id,
            branch_id=branch.id,
            code=str(payload.get("code") or "MAIN"),
            name=str(payload.get("name") or "Main Warehouse"),
            name_ar=payload.get("name_ar") or "المخزن الرئيسي",
            address=payload.get("address"),
            city=payload.get("city"),
            is_active=True,
        )
        self.db.add(warehouse)
        self.db.flush()
        location = WarehouseLocation(
            company_id=company.id,
            warehouse_id=warehouse.id,
            code=str(payload.get("location_code") or "A-01"),
            name=payload.get("location_name") or "Default Location",
            is_active=True,
        )
        self.db.add(location)
        self.db.flush()
        return warehouse

    def _create_fiscal_year(self, company: Company, payload: dict[str, Any]) -> FiscalYear:
        today = date.today()
        start_month = int(payload.get("start_month") or company.fiscal_year_start_month or 1)
        year_label = int(payload.get("year") or today.year)
        start_date = payload.get("start_date") or date(year_label, start_month, 1)
        if payload.get("end_date"):
            end_date = payload["end_date"]
        else:
            end_month = start_month - 1 or 12
            end_year = year_label + (1 if start_month > 1 else 0)
            next_month_first = date(end_year + (1 if end_month == 12 else 0), (end_month % 12) + 1, 1)
            end_date = next_month_first - timedelta(days=1)
        if end_date < start_date:
            raise ValidationFailure("Fiscal year end date must be after its start date")
        year = FiscalCalendarService(self.db, company.id).create_year(
            start_date=start_date, end_date=end_date, name=str(payload.get("name") or f"FY {year_label}"), generate_periods=True
        )
        return year

    def _create_payment_terms(self, company: Company) -> dict[str, PaymentTerm]:
        terms: dict[str, PaymentTerm] = {}
        for code, name, name_ar, days, discount, discount_days in [
            ("CASH", "Cash", "نقدي", 0, None, 0),
            ("NET15", "Net 15 days", "صافي 15 يوم", 15, None, 0),
            ("NET30", "Net 30 days", "صافي 30 يوم", 30, None, 0),
            ("NET60", "Net 60 days", "صافي 60 يوم", 60, None, 0),
            ("NET90", "Net 90 days", "صافي 90 يوم", 90, None, 0),
            ("2-10NET30", "2% 10 days, net 30", "٢٪ خلال ١٠ أيام، صافي ٣٠", 30, Decimal("2"), 10),
        ]:
            term = self.db.execute(
                select(PaymentTerm).where(PaymentTerm.company_id == company.id, PaymentTerm.code == code)
            ).scalars().first()
            if term is None:
                term = PaymentTerm(
                    company_id=company.id,
                    code=code,
                    name=name,
                    name_ar=name_ar,
                    days=days,
                    discount_percent=discount,
                    discount_days=discount_days,
                )
                self.db.add(term)
                self.db.flush()
            terms[code] = term
        return terms

    def _create_taxes(self, company: Company, taxes: Sequence[dict[str, Any]], *, chart_owner: "BootstrapService") -> dict[str, Tax]:
        created: dict[str, Tax] = {}
        chart = {
            code: account_id
            for code, account_id in self.db.execute(
                select(Account.code, Account.id).where(Account.company_id == company.id)
            ).all()
        }
        for item in taxes:
            code = str(item["code"])
            existing = self.db.execute(
                select(Tax).where(Tax.company_id == company.id, Tax.code == code)
            ).scalars().first()
            if existing is not None:
                created[code] = existing
                continue
            tax = Tax(
                company_id=company.id,
                code=code,
                name=item["name"],
                name_ar=item.get("name_ar"),
                tax_type=str(item.get("tax_type", TaxType.SALES.value)),
                computation=str(item.get("computation", TaxComputation.PERCENTAGE.value)),
                inclusion=str(item.get("inclusion", TaxInclusion.EXCLUSIVE.value)),
                rate=Decimal(str(item.get("rate") or 0)),
                fixed_amount=Decimal(str(item.get("fixed_amount") or 0)),
                is_compound=bool(item.get("is_compound", False)),
                applies_to_all_items=bool(item.get("applies_to_all_items", True)),
                recoverable=bool(item.get("recoverable", True)),
                sales_account_id=chart.get(str(item.get("sales_account_code", "2210"))),
                purchase_account_id=chart.get(str(item.get("purchase_account_code", "1410"))),
                withholding_account_id=chart.get(str(item.get("withholding_account_code", "2220"))),
                effective_from=item.get("effective_from"),
                effective_to=item.get("effective_to"),
                is_active=True,
            )
            self.db.add(tax)
            self.db.flush()
            created[code] = tax
        return created

    # ------------------------------------------------------------------- users
    def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        company_id: uuid.UUID,
        roles: Sequence[str] = ("viewer",),
        branch_ids: Sequence[uuid.UUID] = (),
        warehouse_ids: Sequence[uuid.UUID] = (),
        is_superuser: bool = False,
        language: str = "ar",
        job_title: str | None = None,
    ) -> User:
        email = email.strip().lower()
        existing = self.db.execute(select(User).where(User.email == email)).scalars().first()
        if existing is not None:
            raise ConflictError(f"A user with email {email} already exists")
        user = User(
            email=email,
            username=email.split("@")[0],
            password_hash=hash_password(password),
            full_name=full_name,
            job_title=job_title,
            language=language,
            is_active=True,
            is_superuser=is_superuser,
            default_company_id=company_id,
            password_changed_at=datetime.now(UTC),
        )
        self.db.add(user)
        self.db.flush()
        self.grant_company_access(
            user,
            company_id=company_id,
            roles=roles,
            branch_ids=branch_ids,
            warehouse_ids=warehouse_ids,
        )
        return user

    def grant_company_access(
        self,
        user: User,
        *,
        company_id: uuid.UUID,
        roles: Sequence[str],
        branch_ids: Sequence[uuid.UUID] = (),
        warehouse_ids: Sequence[uuid.UUID] = (),
    ) -> None:
        access = self.db.execute(
            select(UserCompanyAccess).where(
                UserCompanyAccess.user_id == user.id, UserCompanyAccess.company_id == company_id
            )
        ).scalars().first()
        if access is None:
            self.db.add(
                UserCompanyAccess(
                    user_id=user.id,
                    company_id=company_id,
                    is_default=True,
                    is_active=True,
                    data_scope="all_branches",
                )
            )
            self.db.flush()
        for role_code in roles:
            role = self.db.execute(
                select(Role).where(Role.company_id == company_id, Role.code == role_code)
            ).scalars().first()
            if role is None:
                raise NotFoundError(f"Role '{role_code}' does not exist")
            exists = self.db.execute(
                select(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role_id == role.id, UserRole.company_id == company_id
                )
            ).scalars().first()
            if exists is None:
                self.db.add(UserRole(user_id=user.id, role_id=role.id, company_id=company_id, granted_at=datetime.now(UTC)))
        for branch_id in branch_ids:
            exists = self.db.execute(
                select(UserBranchAccess).where(
                    UserBranchAccess.user_id == user.id, UserBranchAccess.branch_id == branch_id
                )
            ).scalars().first()
            if exists is None:
                self.db.add(UserBranchAccess(user_id=user.id, company_id=company_id, branch_id=branch_id))
        for warehouse_id in warehouse_ids:
            exists = self.db.execute(
                select(UserWarehouseAccess).where(
                    UserWarehouseAccess.user_id == user.id, UserWarehouseAccess.warehouse_id == warehouse_id
                )
            ).scalars().first()
            if exists is None:
                self.db.add(UserWarehouseAccess(user_id=user.id, company_id=company_id, warehouse_id=warehouse_id))
        self.db.flush()
