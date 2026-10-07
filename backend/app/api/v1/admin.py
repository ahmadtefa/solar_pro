"""Core administration: organisation, currencies, taxes, units, periods, settings.

Thin HTTP layer over the services; every rule stays in the services.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query, status
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailure
from app.core.pagination import snapshot
from app.models.identity import User
from app.models.masterdata import (
    Brand,
    CustomerGroup,
    ProductCategory,
    SupplierGroup,
    Warehouse,
    WarehouseLocation,
    WarehouseZone,
)
from app.models.platform import (
    Address,
    Branch,
    City,
    Company,
    CostCenter,
    Country,
    Currency,
    Department,
    Division,
    DocumentType,
    ExchangeRate,
    FiscalPeriod,
    FiscalYear,
    ModuleActivation,
    NumberSequence,
    PaymentTerm,
    SystemSetting,
    Tax,
    UnitConversion,
    UnitGroup,
    UnitOfMeasure,
)
from app.schemas.masterdata import (
    CompanyCreate,
    CompanyUpdate,
    FiscalYearCreate,
    SettingUpdate,
)
from app.services.accounting_service import FiscalCalendarService, PeriodCloseService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.bootstrap_service import BootstrapService
from app.services.currency_service import CurrencyService
from app.services.numbering_service import NumberingService
from app.services.tax_engine import TaxEngine

router = APIRouter()


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
@router.get("/companies", summary="Companies the signed-in user can access")
def list_companies(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    rows = db.execute(select(Company).where(Company.deleted_at.is_(None)).order_by(Company.code)).scalars().all()
    if not current.is_superuser:
        allowed = {str(item["company_id"]) for item in AuthService(db).accessible_companies(current.user)}
        rows = [row for row in rows if str(row.id) in allowed]
    counts = dict(db.execute(select(Branch.company_id, func.count(Branch.id)).group_by(Branch.company_id)).all())
    return {
        "items": [
            {
                **serialise(
                    row,
                    [
                        "id",
                        "code",
                        "name",
                        "name_ar",
                        "base_currency_code",
                        "country_code",
                        "is_active",
                        "fiscal_year_start_month",
                        "valuation_method",
                        "created_at",
                    ],
                ),
                "branches": int(counts.get(row.id, 0)),
            }
            for row in rows
        ],
        "current_company_id": str(current.company_id) if current.company_id else None,
    }


@router.post("/companies", status_code=status.HTTP_201_CREATED, summary="Create a company and bootstrap its ledger")
def create_company(payload: CompanyCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    if not current.is_superuser:
        current.require("core.company.create")
    bootstrap = BootstrapService(db)
    data = payload.data()
    admin_password = data.pop("admin_password", None)
    admin_email = (data.pop("admin_email", None) or current.user.email).strip().lower()
    admin_full_name = data.pop("admin_full_name", None) or current.user.full_name
    result = bootstrap.create_company(data)
    company: Company = result["company"]
    created_admin: User | None = None
    if admin_password:
        existing = db.execute(select(User).where(User.email == admin_email)).scalars().first()
        created_admin = existing or bootstrap.create_user(
            email=admin_email,
            password=admin_password,
            full_name=admin_full_name,
            company_id=company.id,
            roles=("company_admin",),
        )
    AuditService(db, audit_context(current)).log_create(company, entity_type="company", label=company.code)
    return {
        "id": str(company.id),
        "code": company.code,
        "name": company.name,
        "branch_id": str(result["branch"].id),
        "warehouse_id": str(result["warehouse"].id),
        "fiscal_year_id": str(result["fiscal_year"].id),
        "admin_user_id": str(created_admin.id) if created_admin else None,
    }


@router.get("/companies/{company_id}", summary="Company profile")
def get_company(company_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    company = db.get(Company, company_id)
    if company is None or company.deleted_at is not None:
        raise NotFoundError("Company not found", id=str(company_id))
    if not current.is_superuser:
        _require_company_access(db, current, company_id)
    return serialise(company)


@router.patch("/companies/{company_id}", summary="Update a company profile")
def update_company(company_id: uuid.UUID, payload: CompanyUpdate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    if not current.is_superuser:
        _require_company_access(db, current, company_id)
        current.require("core.company.edit")
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found", id=str(company_id))
    before = snapshot(company)
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changed.items():
        if hasattr(company, key):
            setattr(company, key, value)
    db.flush()
    AuditService(db, audit_context(current)).log_update(company, before, entity_type="company", label=company.code)
    return serialise(company)


@router.get("/companies/{company_id}/modules", summary="Enabled modules per company")
def list_modules(company_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _require_company_access(db, current, company_id)
    rows = db.execute(select(ModuleActivation).where(ModuleActivation.company_id == company_id)).scalars().all()
    return {
        "items": [
            {"module_key": row.module_key, "is_enabled": row.is_enabled, "settings": row.settings_json}
            for row in rows
        ]
    }


@router.put("/companies/{company_id}/modules/{module_key}", summary="Enable or disable a module")
def set_module(
    company_id: uuid.UUID,
    module_key: str,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    current.require("core.module.edit")
    _require_company_access(db, current, company_id)
    row = db.execute(
        select(ModuleActivation).where(
            ModuleActivation.company_id == company_id, ModuleActivation.module_key == module_key
        )
    ).scalars().first()
    enabled = bool(payload.get("is_enabled", True))
    settings_json = payload.get("settings") or {}
    if row is None:
        row = ModuleActivation(
            company_id=company_id, module_key=module_key, is_enabled=enabled, settings_json=settings_json
        )
        db.add(row)
    else:
        row.is_enabled = enabled
        row.settings_json = settings_json
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "update", row, entity_type="module_activation", label=module_key, new_values={"is_enabled": enabled}
    )
    return {"module_key": module_key, "is_enabled": enabled}


# --------------------------------------------------------------------------- #
# Organisation
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="branches",
            model=Branch,
            module="core",
            entity="branch",
            search_fields=["code", "name", "name_ar", "phone"],
            label_field="name",
            filters={"is_active": "is_active", "city_id": "city_id"},
            create_handler=guarded_create(Branch, unique=[("code", "Branch code")]),
        ),
        tags=["core"],
    ),
    prefix="/branches",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="departments",
            model=Department,
            module="core",
            entity="department",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"branch_id": "branch_id", "is_active": "is_active"},
            create_handler=guarded_create(Department, unique=[("code", "Department code")]),
        ),
        tags=["core"],
    ),
    prefix="/departments",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="divisions",
            model=Division,
            module="core",
            entity="division",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"branch_id": "branch_id"},
            create_handler=guarded_create(Division, unique=[("code", "Division code")]),
        ),
        tags=["core"],
    ),
    prefix="/divisions",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="cost-centers",
            model=CostCenter,
            module="core",
            entity="cost_center",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"branch_id": "branch_id", "is_active": "is_active"},
            create_handler=guarded_create(CostCenter, unique=[("code", "Cost center code")]),
        ),
        tags=["core"],
    ),
    prefix="/cost-centers",
)

# --------------------------------------------------------------------------- #
# Geography and addresses
# --------------------------------------------------------------------------- #
@router.get("/countries", summary="Country picker data")
def list_countries(db: DB, current: CurrentUserDep, q: str | None = None) -> dict[str, Any]:
    stmt = select(Country).order_by(Country.name)
    if q:
        stmt = stmt.where(Country.name.ilike(f"%{q}%") | Country.code.ilike(f"%{q}%"))
    rows = db.execute(stmt.limit(300)).scalars().all()
    return {"items": [serialise(row) for row in rows]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="cities",
            model=City,
            module="core",
            entity="city",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"country_code": "country_code", "is_active": "is_active"},
            create_handler=guarded_create(City),
        ),
        tags=["core"],
    ),
    prefix="/cities",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="addresses",
            model=Address,
            module="core",
            entity="address",
            search_fields=["label", "address_line1", "city"],
            label_field="label",
            filters={"party_type": "party_type", "party_id": "party_id"},
            soft_delete=False,
        ),
        tags=["core"],
    ),
    prefix="/addresses",
)

# --------------------------------------------------------------------------- #
# Currencies and exchange rates
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="currencies",
            model=Currency,
            module="core",
            entity="currency",
            search_fields=["code", "name", "name_ar"],
            label_field="code",
            default_sort="code",
            soft_delete=False,
            create_handler=guarded_create(Currency, unique=[("code", "Currency code")]),
        ),
        tags=["core"],
    ),
    prefix="/currencies",
)


@router.get("/exchange-rates/latest", summary="Latest rate for each currency")
def latest_rates(db: DB, current: CurrentUserDep, base: str | None = None) -> dict[str, Any]:
    current.require("core.exchange_rate.view")
    service = CurrencyService(db, current.company_id)
    return {"base_currency": (base or service.base_currency).upper(), "items": service.latest_rates(base=base)}


@router.get("/exchange-rates/convert", summary="Convert an amount with the historical rate table")
def convert_amount(
    db: DB,
    current: CurrentUserDep,
    amount: str = Query(...),
    from_currency: str = Query(...),
    to_currency: str = Query(...),
    on_date: str | None = None,
) -> dict[str, Any]:
    from datetime import date as date_type

    current.require("core.exchange_rate.view")
    parsed = date_type.fromisoformat(on_date) if on_date else None
    result = CurrencyService(db, current.company_id).convert(
        Decimal(amount), from_currency, to_currency, on_date=parsed
    )
    payload = {key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()}
    payload.update(
        {
            "source_amount": amount,
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "on_date": (parsed or date_type.today()).isoformat(),
        }
    )
    return payload


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="exchange-rates",
            model=ExchangeRate,
            module="core",
            entity="exchange_rate",
            search_fields=["currency_code"],
            default_sort="effective_from",
            soft_delete=False,
            filters={"currency_code": "currency_code", "rate_type": "rate_type"},
            create_handler=guarded_create(ExchangeRate),
        ),
        tags=["core"],
    ),
    prefix="/exchange-rates",
)

# --------------------------------------------------------------------------- #
# Tax engine
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="taxes",
            model=Tax,
            module="core",
            entity="tax",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"tax_type": "tax_type", "is_active": "is_active"},
            create_handler=guarded_create(Tax, unique=[("code", "Tax code")]),
        ),
        tags=["core"],
    ),
    prefix="/taxes",
)


@router.post("/taxes/calculate", summary="Preview a tax computation for an amount")
def calculate_tax(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.tax.view")
    amount = Decimal(str(payload.get("amount", "0")))
    tax_ids = [uuid.UUID(str(item)) for item in (payload.get("tax_ids") or [])]
    codes = payload.get("tax_codes") or ([payload["tax_code"]] if payload.get("tax_code") else [])
    engine = TaxEngine(db, current.company_id)
    if codes and not tax_ids:
        rows = db.execute(
            select(Tax).where(Tax.company_id == current.company_id, Tax.code.in_([str(c).upper() for c in codes]))
        ).scalars().all()
        tax_ids = [row.id for row in rows]
    breakdown = engine.apply_many(
        amount, tax_ids, prices_include_tax=bool(payload.get("prices_include_tax", False))
    )
    return {"amount": str(amount), "tax_codes": codes, **breakdown.as_dict()}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="payment-terms",
            model=PaymentTerm,
            module="core",
            entity="payment_term",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(PaymentTerm, unique=[("code", "Payment term code")]),
        ),
        tags=["core"],
    ),
    prefix="/payment-terms",
)

# --------------------------------------------------------------------------- #
# Units of measure
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="unit-groups",
            model=UnitGroup,
            module="core",
            entity="unit_group",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(UnitGroup, unique=[("code", "Unit group code")]),
        ),
        tags=["core"],
    ),
    prefix="/unit-groups",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="units",
            model=UnitOfMeasure,
            module="core",
            entity="unit",
            search_fields=["code", "name", "name_ar", "symbol"],
            label_field="name",
            filters={"unit_group_id": "unit_group_id", "is_active": "is_active"},
            create_handler=guarded_create(UnitOfMeasure, unique=[("code", "Unit code")]),
        ),
        tags=["core"],
    ),
    prefix="/units",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="unit-conversions",
            model=UnitConversion,
            module="core",
            entity="unit_conversion",
            filters={"from_unit_id": "from_unit_id", "to_unit_id": "to_unit_id"},
            create_handler=guarded_create(UnitConversion),
        ),
        tags=["core"],
    ),
    prefix="/unit-conversions",
)

# --------------------------------------------------------------------------- #
# Fiscal calendar
# --------------------------------------------------------------------------- #
@router.get("/fiscal-years", summary="Fiscal years with their periods")
def list_fiscal_years(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.fiscal_year.view")
    years = db.execute(
        select(FiscalYear)
        .where(FiscalYear.company_id == current.company_id, FiscalYear.deleted_at.is_(None))
        .order_by(FiscalYear.start_date.desc())
    ).scalars().all()
    periods = db.execute(
        select(FiscalPeriod).where(FiscalPeriod.company_id == current.company_id).order_by(FiscalPeriod.period_number)
    ).scalars().all()
    by_year: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for period in periods:
        by_year.setdefault(period.fiscal_year_id, []).append(
            {
                "id": str(period.id),
                "period_number": period.period_number,
                "name": period.name,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "is_closed": period.is_closed,
            }
        )
    return {"items": [{**serialise(year), "periods": by_year.get(year.id, [])} for year in years]}


@router.post("/fiscal-years", status_code=status.HTTP_201_CREATED, summary="Create a fiscal year with monthly periods")
def create_fiscal_year(payload: FiscalYearCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.fiscal_year.create")
    calendar = FiscalCalendarService(db, current.company_id)
    year = calendar.create_year(
        start_date=payload.start_date, end_date=payload.end_date, name=payload.name, generate_periods=True
    )
    periods = db.execute(
        select(func.count(FiscalPeriod.id)).where(FiscalPeriod.fiscal_year_id == year.id)
    ).scalar_one()
    AuditService(db, audit_context(current)).log_create(year, entity_type="fiscal_year", label=year.code)
    return {"id": str(year.id), "code": year.code, "periods": int(periods)}


@router.post("/fiscal-years/{year_id}/close", summary="Close a fiscal year and roll the result to retained earnings")
def close_fiscal_year(year_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.fiscal_year.close")
    year = db.get(FiscalYear, year_id)
    if year is None or year.company_id != current.company_id:
        raise NotFoundError("Fiscal year not found", id=str(year_id))
    result = PeriodCloseService(db, current.company_id, user_id=current.id).close_year(year_id)
    AuditService(db, audit_context(current)).log_action(
        "close", year, entity_type="fiscal_year", label=year.code, remarks="year closed", new_values=result
    )
    return result


@router.post("/fiscal-periods/{period_id}/close", summary="Close or reopen a fiscal period")
def set_period_state(
    period_id: uuid.UUID, db: DB, current: CurrentUserDep, reopen: bool = False, reason: str | None = None
) -> dict[str, Any]:
    current.require("core.fiscal_period.close")
    period = db.get(FiscalPeriod, period_id)
    if period is None or period.company_id != current.company_id:
        raise NotFoundError("Fiscal period not found", id=str(period_id))
    calendar = FiscalCalendarService(db, current.company_id)
    if reopen:
        calendar.reopen_period(period_id, reason=reason or "reopened by administrator")
    else:
        calendar.close_period(period_id, reason=reason)
    AuditService(db, audit_context(current)).log_action(
        "close" if not reopen else "reopen", period, entity_type="fiscal_period", label=period.name
    )
    return {"id": str(period.id), "is_closed": period.is_closed}


# --------------------------------------------------------------------------- #
# Numbering and document types
# --------------------------------------------------------------------------- #
@router.get("/number-sequences", summary="Document numbering sequences")
def list_sequences(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.number_sequence.view")
    rows = db.execute(
        select(NumberSequence)
        .where(NumberSequence.company_id == current.company_id)
        .order_by(NumberSequence.document_type)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@router.put("/number-sequences/{document_type}", summary="Configure the numbering of a document type")
def upsert_sequence(
    document_type: str, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("core.number_sequence.edit")
    branch_id = payload.get("branch_id")
    sequence = NumberingService(db, current.company_id).configure(
        document_type,
        prefix=payload.get("prefix"),
        suffix=payload.get("suffix"),
        padding=payload.get("padding"),
        reset_yearly=payload.get("reset_yearly"),
        branch_id=uuid.UUID(str(branch_id)) if branch_id else None,
    )
    AuditService(db, audit_context(current)).log_action(
        "update", sequence, entity_type="number_sequence", label=document_type
    )
    return serialise(sequence)


@router.get("/number-sequences/{document_type}/next", summary="Preview the next number")
def preview_next(document_type: str, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.number_sequence.view")
    preview = NumberingService(db, current.company_id).peek_next(document_type)
    return {"document_type": document_type, "next_number": preview}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="document-types",
            model=DocumentType,
            module="core",
            entity="document_type",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(DocumentType, unique=[("code", "Document type code")]),
        ),
        tags=["core"],
    ),
    prefix="/document-types",
)

# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@router.get("/settings", summary="Company settings grouped by category")
def list_settings(db: DB, current: CurrentUserDep, category: str | None = None) -> dict[str, Any]:
    current.require("core.system_setting.view")
    stmt = select(SystemSetting).where(SystemSetting.company_id == current.company_id)
    if category:
        stmt = stmt.where(SystemSetting.category == category)
    rows = db.execute(stmt.order_by(SystemSetting.category, SystemSetting.key)).scalars().all()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        grouped.setdefault(row.category or "general", {})[row.key] = (
            row.value_json if row.value_json is not None else row.value
        )
    return {"items": [serialise(row) for row in rows], "grouped": grouped}


@router.put("/settings", summary="Upsert one or many settings")
def update_settings(
    db: DB, current: CurrentUserDep, payload: list[SettingUpdate] | SettingUpdate = Body(...)
) -> dict[str, Any]:
    current.require("core.system_setting.edit")
    items = payload if isinstance(payload, list) else [payload]
    saved = 0
    for item in items:
        row = db.execute(
            select(SystemSetting).where(
                SystemSetting.company_id == current.company_id, SystemSetting.key == item.key
            )
        ).scalars().first()
        value = item.value
        is_json = isinstance(value, (dict, list))
        if row is None:
            row = SystemSetting(
                company_id=current.company_id,
                key=item.key,
                category=item.category or "general",
                scope=item.scope,
                value=None if is_json else (None if value is None else str(value)),
                value_json=value if is_json else None,
            )
            db.add(row)
        else:
            row.value = None if is_json else (None if value is None else str(value))
            row.value_json = value if is_json else None
            if item.category:
                row.category = item.category
        saved += 1
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "update",
        None,
        entity_type="system_setting",
        label="settings",
        new_values={"keys": [item.key for item in items]},
    )
    return {"saved": saved}


# --------------------------------------------------------------------------- #
# Categories, brands and grouping masters
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="product-categories",
            model=ProductCategory,
            module="inventory",
            entity="product_category",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(ProductCategory, unique=[("code", "Category code")]),
        ),
        tags=["inventory"],
    ),
    prefix="/product-categories",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="brands",
            model=Brand,
            module="inventory",
            entity="brand",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(Brand, unique=[("code", "Brand code")]),
        ),
        tags=["inventory"],
    ),
    prefix="/brands",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="customer-groups",
            model=CustomerGroup,
            module="crm",
            entity="customer_group",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(CustomerGroup, unique=[("code", "Customer group code")]),
        ),
        tags=["crm"],
    ),
    prefix="/customer-groups",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="supplier-groups",
            model=SupplierGroup,
            module="suppliers",
            entity="supplier_group",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(SupplierGroup, unique=[("code", "Supplier group code")]),
        ),
        tags=["suppliers"],
    ),
    prefix="/supplier-groups",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="warehouse-zones",
            model=WarehouseZone,
            module="inventory",
            entity="warehouse_zone",
            search_fields=["code", "name"],
            label_field="name",
            filters={"warehouse_id": "warehouse_id"},
            create_handler=guarded_create(WarehouseZone),
        ),
        tags=["inventory"],
    ),
    prefix="/warehouse-zones",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="warehouse-locations",
            model=WarehouseLocation,
            module="inventory",
            entity="warehouse_location",
            search_fields=["code", "name", "barcode"],
            label_field="code",
            filters={"warehouse_id": "warehouse_id", "zone_id": "zone_id"},
            create_handler=guarded_create(WarehouseLocation),
        ),
        tags=["inventory"],
    ),
    prefix="/warehouse-locations",
)


# --------------------------------------------------------------------------- #
# Pickers
# --------------------------------------------------------------------------- #
_LOOKUPS: dict[str, tuple[type[Any], str]] = {
    "branches": (Branch, "core.branch.view"),
    "departments": (Department, "core.department.view"),
    "cost-centers": (CostCenter, "core.cost_center.view"),
    "currencies": (Currency, "core.currency.view"),
    "taxes": (Tax, "core.tax.view"),
    "payment-terms": (PaymentTerm, "core.payment_term.view"),
    "units": (UnitOfMeasure, "core.unit.view"),
    "warehouses": (Warehouse, "inventory.warehouse.view"),
    "fiscal-years": (FiscalYear, "core.fiscal_year.view"),
    "document-types": (DocumentType, "core.document_type.view"),
    "countries": (Country, "core.country.view"),
}


@router.get("/lookups/{kind}", summary="Lightweight option lists for UI pickers")
def lookup(
    kind: str,
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    entry = _LOOKUPS.get(kind)
    if entry is None:
        raise ValidationFailure(f"Unknown lookup '{kind}'", available=sorted(_LOOKUPS))
    model, permission = entry
    current.require(permission)
    stmt = select(model)
    if hasattr(model, "company_id"):
        stmt = stmt.where(model.company_id == current.company_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    if hasattr(model, "is_active"):
        stmt = stmt.where(model.is_active.is_(True))
    if q:
        column = getattr(model, "name", None) or model.code
        stmt = stmt.where(column.ilike(f"%{q}%"))
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "items": [
            {
                "id": str(row.id),
                "code": getattr(row, "code", None),
                "name": getattr(row, "name", None) or getattr(row, "code", None),
                "extra": _lookup_extra(row),
            }
            for row in rows
        ]
    }


def _lookup_extra(row: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for field in ("is_head_office", "symbol", "rate", "days", "is_base", "base_currency_code", "status"):
        if hasattr(row, field):
            value = getattr(row, field)
            extra[field] = str(value) if value is not None and not isinstance(value, (bool, int, str)) else value
    return extra


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_company_access(db: DB, current: CurrentUserDep, company_id: uuid.UUID) -> None:
    if current.is_superuser:
        return
    allowed = {item["company_id"] for item in AuthService(db).accessible_companies(current.user)}
    if company_id not in allowed:
        raise PermissionDeniedError("You do not have access to this company")


def bootstrap_status(db: DB) -> dict[str, Any]:
    companies = db.execute(select(func.count(Company.id))).scalar_one()
    users = db.execute(select(func.count(User.id))).scalar_one()
    return {"needs_setup": companies == 0 or users == 0, "companies": int(companies), "users": int(users)}


__all__ = ["bootstrap_status", "router"]
