"""Organisation structure and core master data: branches, departments, currencies, taxes."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import (
    ResourceSpec,
    build_crud_router,
    guarded_create,
    guarded_update,
    serialise,
)
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.models.platform import (
    Address,
    Branch,
    City,
    CostCenter,
    Country,
    Currency,
    Department,
    Division,
    DocumentType,
    ExchangeRate,
    FiscalPeriod,
    FiscalYear,
    NumberSequence,
    PaymentTerm,
    SystemSetting,
    Tax,
    UnitConversion,
    UnitGroup,
    UnitOfMeasure,
)
from app.services.audit_service import AuditService
from app.services.currency_service import CurrencyService
from app.services.numbering_service import NumberingService

router = APIRouter()

# --------------------------------------------------------------------------- #
# Branch / department / division structures
# --------------------------------------------------------------------------- #
branch_router = build_crud_router(
    ResourceSpec(
        name="branches",
        model=Branch,
        module="core",
        entity="branch",
        search_fields=["code", "name", "name_ar"],
        label_field="name",
        create_handler=guarded_create(Branch, unique=[("code", "Branch code")]),
        update_handler=guarded_update(Branch),
    ),
    tags=["master-data"],
)
router.include_router(branch_router, prefix="/branches")

router.include_router(
    build_crud_router(
        ResourceSpec(
            name="departments",
            model=Department,
            module="core",
            entity="department",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            filters={"branch_id": "branch_id", "parent_id": "parent_id"},
            create_handler=guarded_create(Department),
            update_handler=guarded_update(Department),
        ),
        tags=["master-data"],
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
            search_fields=["code", "name"],
            label_field="name",
            filters={"department_id": "department_id", "branch_id": "branch_id"},
            create_handler=guarded_create(Division),
        ),
        tags=["master-data"],
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
            filters={"branch_id": "branch_id", "parent_id": "parent_id", "is_active": "is_active"},
            create_handler=guarded_create(CostCenter, unique=[("code", "Cost centre code")]),
        ),
        tags=["master-data"],
    ),
    prefix="/cost-centers",
)

# --------------------------------------------------------------------------- #
# Geography
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="countries",
            model=Country,
            module="core",
            entity="country",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            soft_delete=False,
            create_handler=guarded_create(Country, unique=[("code", "Country code")]),
        ),
        tags=["master-data"],
    ),
    prefix="/geo/countries",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="cities",
            model=City,
            module="core",
            entity="city",
            search_fields=["name", "name_ar"],
            label_field="name",
            filters={"country_id": "country_id"},
            soft_delete=False,
            create_handler=guarded_create(City),
        ),
        tags=["master-data"],
    ),
    prefix="/geo/cities",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="addresses",
            model=Address,
            module="core",
            entity="address",
            search_fields=["label", "line1", "city_name"],
            label_field="label",
            filters={"party_type": "party_type", "party_id": "party_id", "city_id": "city_id"},
            soft_delete=False,
            create_handler=guarded_create(Address),
        ),
        tags=["master-data"],
    ),
    prefix="/geo/addresses",
)


# --------------------------------------------------------------------------- #
# Currencies and exchange rates
# --------------------------------------------------------------------------- #
@router.get("/currencies", summary="Currencies")
def list_currencies(db: DB, current: CurrentUserDep, active_only: bool = False) -> dict[str, Any]:
    current.require("core.currency.view")
    stmt = select(Currency)
    if active_only:
        stmt = stmt.where(Currency.is_active.is_(True))
    rows = db.execute(stmt.order_by(Currency.code)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/currencies", status_code=201, summary="Create a currency")
def create_currency(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.currency.create")
    if not payload.get("code"):
        raise ValidationFailure("A currency code is required")
    existing = db.execute(select(Currency).where(Currency.code == str(payload["code"]).upper())).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Currency already exists", code=payload["code"])
    currency = Currency(
        code=str(payload["code"]).upper()[:8],
        name=payload.get("name") or payload["code"],
        name_ar=payload.get("name_ar"),
        symbol=payload.get("symbol"),
        decimal_places=int(payload.get("decimal_places") or 2),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(currency)
    db.flush()
    AuditService(db, audit_context(current)).log_create(currency, entity_type="currency", label=currency.code)
    return serialise(currency)


@router.patch("/currencies/{code}", summary="Update a currency")
def update_currency(code: str, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.currency.edit")
    currency = db.execute(select(Currency).where(Currency.code == code.upper())).scalar_one_or_none()
    if currency is None:
        raise NotFoundError("Currency not found", code=code)
    for field in ("name", "name_ar", "symbol", "decimal_places", "is_active"):
        if field in payload and payload[field] is not None:
            setattr(currency, field, payload[field])
    db.flush()
    return serialise(currency)


@router.get("/exchange-rates", summary="Exchange rates effective for a currency")
def list_rates(
    db: DB,
    current: CurrentUserDep,
    currency_code: str | None = None,
    on_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("core.exchange_rate.view")
    stmt = select(ExchangeRate).where(ExchangeRate.company_id == current.company_id)
    if currency_code:
        stmt = stmt.where(ExchangeRate.currency_code == currency_code.upper())
    if on_date:
        stmt = stmt.where(
            ExchangeRate.effective_from <= on_date,
            (ExchangeRate.effective_to.is_(None)) | (ExchangeRate.effective_to >= on_date),
        )
    rows = db.execute(stmt.order_by(ExchangeRate.effective_from.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/exchange-rates", status_code=201, summary="Set an exchange rate")
def create_rate(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.exchange_rate.create")
    code = payload.get("currency_code") or payload.get("code")
    rate_value = payload.get("rate")
    if not code or rate_value in (None, ""):
        raise ValidationFailure("currency_code and rate are required")
    amount = Decimal(str(rate_value))
    if amount <= 0:
        raise ValidationFailure("The rate must be greater than zero")
    service = CurrencyService(db, current.company_id)
    row = service.upsert_rate(
        currency_code=str(code).upper(),
        rate=amount,
        base_currency_code=(payload.get("base_currency_code") or None),
        effective_from=_date(payload.get("effective_from") or payload.get("rate_date")) or date.today(),
        effective_to=_date(payload.get("effective_to")),
        rate_type=payload.get("rate_type") or "spot",
    )
    db.flush()
    AuditService(db, audit_context(current)).log_create(row, entity_type="exchange_rate", label=row.currency_code)
    return serialise(row)


@router.get("/exchange-rates/latest/{currency_code}", summary="Latest rate of a currency")
def latest_rate(currency_code: str, db: DB, current: CurrentUserDep, on_date: date | None = None) -> dict[str, Any]:
    current.require("core.exchange_rate.view")
    service = CurrencyService(db, current.company_id)
    rate = service.rate(currency_code, on_date=on_date)
    base = service.base_currency
    base_code = base.code if hasattr(base, "code") else str(base)
    return {
        "currency_code": currency_code.upper(),
        "rate": str(rate),
        "base_currency": base_code,
        "on_date": (on_date or date.today()).isoformat(),
    }


@router.get("/exchange-rates/convert", summary="Convert an amount between currencies")
def convert_amount(
    db: DB,
    current: CurrentUserDep,
    amount: str = Query(...),
    from_currency: str = Query(...),
    to_currency: str = Query(...),
    on_date: date | None = None,
) -> dict[str, Any]:
    current.require("core.exchange_rate.view")
    result = CurrencyService(db, current.company_id).convert(
        Decimal(amount),
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        on_date=on_date,
    )
    return {
        "amount": amount,
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "on_date": (on_date or date.today()).isoformat(),
        **{key: str(value) for key, value in result.items() if key != "on_date"},
    }


# --------------------------------------------------------------------------- #
# Taxes and payment terms
# --------------------------------------------------------------------------- #
@router.get("/taxes", summary="Configurable tax codes")
def list_taxes(db: DB, current: CurrentUserDep, active_only: bool = True) -> dict[str, Any]:
    current.require("core.tax.view")
    stmt = select(Tax).where(Tax.company_id == current.company_id, Tax.deleted_at.is_(None))
    if active_only:
        stmt = stmt.where(Tax.is_active.is_(True))
    rows = db.execute(stmt.order_by(Tax.code)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/taxes", status_code=201, summary="Create a tax")
def create_tax(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.tax.create")
    if not payload.get("code") or not payload.get("name"):
        raise ValidationFailure("code and name are required")
    tax = Tax(
        company_id=current.company_id,
        code=str(payload["code"]).upper()[:32],
        name=payload["name"],
        name_ar=payload.get("name_ar"),
        tax_type=payload.get("tax_type") or "vat",
        computation=payload.get("computation") or "percentage",
        inclusion=payload.get("inclusion") or "exclusive",
        rate=Decimal(str(payload.get("rate") or 0)),
        fixed_amount=Decimal(str(payload.get("fixed_amount") or 0)),
        is_compound=bool(payload.get("is_compound", False)),
        applies_to_all_items=bool(payload.get("applies_to_all_items", True)),
        recoverable=bool(payload.get("recoverable", True)),
        sales_account_id=_uuid(payload.get("sales_account_id")),
        purchase_account_id=_uuid(payload.get("purchase_account_id")),
        withholding_account_id=_uuid(payload.get("withholding_account_id")),
        effective_from=_date(payload.get("effective_from")),
        effective_to=_date(payload.get("effective_to")),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(tax)
    db.flush()
    AuditService(db, audit_context(current)).log_create(tax, entity_type="tax", label=tax.code)
    return serialise(tax)


@router.patch("/taxes/{tax_id}", summary="Update a tax")
def update_tax(tax_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.tax.edit")
    tax = db.get(Tax, tax_id)
    if tax is None or tax.company_id != current.company_id:
        raise NotFoundError("Tax not found", id=str(tax_id))
    for field in (
        "name",
        "name_ar",
        "tax_type",
        "computation",
        "inclusion",
        "is_compound",
        "applies_to_all_items",
        "recoverable",
        "is_active",
    ):
        if field in payload and payload[field] is not None:
            setattr(tax, field, payload[field])
    for field in ("rate", "fixed_amount"):
        if payload.get(field) is not None:
            setattr(tax, field, Decimal(str(payload[field])))
    for field in ("sales_account_id", "purchase_account_id", "withholding_account_id"):
        if field in payload:
            setattr(tax, field, _uuid(payload[field]))
    db.flush()
    return serialise(tax)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="payment-terms",
            model=PaymentTerm,
            module="core",
            entity="payment_term",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(PaymentTerm),
            update_handler=guarded_update(PaymentTerm),
        ),
        tags=["master-data"],
    ),
    prefix="/payment-terms",
)

# --------------------------------------------------------------------------- #
# Units of measure and conversions
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
        tags=["master-data"],
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
            filters={"unit_group_id": "unit_group_id", "is_base": "is_base", "is_active": "is_active"},
            create_handler=guarded_create(UnitOfMeasure, unique=[("code", "Unit code")]),
            update_handler=guarded_update(UnitOfMeasure),
        ),
        tags=["master-data"],
    ),
    prefix="/units",
)


@router.post("/unit-conversions", status_code=201, summary="Define a conversion factor between two units")
def create_conversion(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.unit.create")
    from_unit_id = _uuid(payload.get("from_unit_id"))
    to_unit_id = _uuid(payload.get("to_unit_id"))
    if not from_unit_id or not to_unit_id:
        raise ValidationFailure("from_unit_id and to_unit_id are required")
    if from_unit_id == to_unit_id:
        raise ValidationFailure("A unit cannot be converted to itself")
    factor = Decimal(str(payload.get("factor") or 0))
    if factor <= 0:
        raise ValidationFailure("The conversion factor must be greater than zero")
    existing = db.execute(
        select(UnitConversion).where(
            UnitConversion.company_id == current.company_id,
            UnitConversion.from_unit_id == from_unit_id,
            UnitConversion.to_unit_id == to_unit_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.factor = factor
        db.flush()
        return serialise(existing)
    conversion = UnitConversion(
        company_id=current.company_id, from_unit_id=from_unit_id, to_unit_id=to_unit_id, factor=factor, is_active=True
    )
    db.add(conversion)
    db.flush()
    return serialise(conversion)


@router.get("/unit-conversions", summary="Conversion factors")
def list_conversions(
    db: DB, current: CurrentUserDep, from_unit_id: uuid.UUID | None = None
) -> dict[str, Any]:
    current.require("core.unit.view")
    stmt = select(UnitConversion).where(
        UnitConversion.company_id == current.company_id, UnitConversion.deleted_at.is_(None)
    )
    if from_unit_id:
        stmt = stmt.where(UnitConversion.from_unit_id == from_unit_id)
    rows = db.execute(stmt).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/unit-conversions/convert", summary="Convert a quantity between two units")
def convert_quantity(
    db: DB,
    current: CurrentUserDep,
    quantity_value: str = Query(...),
    from_unit_id: uuid.UUID = Query(...),
    to_unit_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    current.require("core.unit.view")
    value = Decimal(quantity_value)
    if from_unit_id == to_unit_id:
        return {"quantity": quantity_value, "converted": str(value)}
    direct = db.execute(
        select(UnitConversion).where(
            UnitConversion.company_id == current.company_id,
            UnitConversion.from_unit_id == from_unit_id,
            UnitConversion.to_unit_id == to_unit_id,
        )
    ).scalar_one_or_none()
    if direct is not None:
        return {"quantity": quantity_value, "converted": str(value * direct.factor), "factor": str(direct.factor)}
    reverse = db.execute(
        select(UnitConversion).where(
            UnitConversion.company_id == current.company_id,
            UnitConversion.from_unit_id == to_unit_id,
            UnitConversion.to_unit_id == from_unit_id,
        )
    ).scalar_one_or_none()
    if reverse is not None and reverse.factor:
        return {"quantity": quantity_value, "converted": str(value / reverse.factor), "factor": str(reverse.factor)}
    raise NotFoundError("No conversion factor defined between these units")

# --------------------------------------------------------------------------- #
# Fiscal calendar
# --------------------------------------------------------------------------- #
@router.get("/fiscal-years", summary="Fiscal years with their status")
def list_fiscal_years(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.fiscal_year.view")
    rows = db.execute(
        select(FiscalYear)
        .where(FiscalYear.company_id == current.company_id, FiscalYear.deleted_at.is_(None))
        .order_by(FiscalYear.start_date.desc())
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/fiscal-years", status_code=201, summary="Create a fiscal year with its periods")
def create_fiscal_year(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.fiscal_year.create")
    start = _date(payload.get("start_date"))
    end = _date(payload.get("end_date"))
    if not start or not end:
        raise ValidationFailure("start_date and end_date are required")
    if end <= start:
        raise ValidationFailure("end_date must be after start_date")
    year = FiscalYear(
        company_id=current.company_id,
        code=payload.get("code") or str(start.year),
        name=payload.get("name") or f"FY {start.year}",
        start_date=start,
        end_date=end,
        status=payload.get("status") or "open",
        is_closed=False,
    )
    db.add(year)
    db.flush()
    created = 0
    if payload.get("months", True):
        created = _generate_periods(db, current.company_id, year, start, end)
    db.flush()
    AuditService(db, audit_context(current)).log_create(year, entity_type="fiscal_year", label=year.code)
    return {**serialise(year), "periods_created": created}


def _generate_periods(
    db: DB, company_id: uuid.UUID, year: FiscalYear, start: date, end: date, *, months: int = 12
) -> int:
    cursor = start
    created = 0
    number = 1
    while cursor <= end and number <= months:
        period_end = _add_months(cursor, 1)
        period_end = min(period_end - _one_day(), end)
        db.add(
            FiscalPeriod(
                company_id=company_id,
                fiscal_year_id=year.id,
                period_number=number,
                name=f"{number:02d}",
                start_date=cursor,
                end_date=period_end,
                is_closed=False,
            )
        )
        created += 1
        cursor = period_end + _one_day()
        number += 1
    return created


@router.get("/fiscal-periods", summary="Fiscal periods")
def list_fiscal_periods(
    db: DB, current: CurrentUserDep, fiscal_year_id: uuid.UUID | None = None
) -> dict[str, Any]:
    current.require("core.fiscal_period.view")
    stmt = select(FiscalPeriod).where(FiscalPeriod.company_id == current.company_id)
    if fiscal_year_id:
        stmt = stmt.where(FiscalPeriod.fiscal_year_id == fiscal_year_id)
    rows = db.execute(stmt.order_by(FiscalPeriod.start_date)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/fiscal-periods/{period_id}/close", summary="Close a fiscal period")
def close_period(
    period_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("core.fiscal_period.edit")
    period = db.get(FiscalPeriod, period_id)
    if period is None or period.company_id != current.company_id:
        raise NotFoundError("Fiscal period not found", id=str(period_id))
    if period.is_closed:
        raise ConflictError("Period is already closed")
    period.is_closed = True
    import datetime as dt

    period.closed_at = dt.datetime.now(dt.UTC)
    db.flush()
    AuditService(db, audit_context(current)).log_update(
        period,
        {"is_closed": False},
        entity_type="fiscal_period",
        label=period.name,
        action="period_closed",
    )
    return serialise(period)


@router.post("/fiscal-periods/{period_id}/reopen", summary="Reopen a fiscal period")
def reopen_period(
    period_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("core.fiscal_period.edit")
    if not payload.get("reason"):
        raise ValidationFailure("A reason is required to reopen a period")
    period = db.get(FiscalPeriod, period_id)
    if period is None or period.company_id != current.company_id:
        raise NotFoundError("Fiscal period not found", id=str(period_id))
    period.is_closed = False
    period.closed_at = None
    db.flush()
    AuditService(db, audit_context(current)).log_update(
        period, {"is_closed": True}, entity_type="fiscal_period", label=period.name, action="period_reopened"
    )
    return serialise(period)


@router.post("/fiscal-years/{year_id}/close", summary="Year-end close with retained earnings posting")
def close_fiscal_year(
    year_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("core.fiscal_year.edit")
    from app.services.accounting_service import PeriodCloseService

    service = PeriodCloseService(db, current.company_id, user_id=current.id, audit_context=audit_context(current))
    result = service.close_year(year_id, retained_earnings_account_id=_uuid(payload.get("retained_earnings_account_id")))
    db.flush()
    return result if isinstance(result, dict) else serialise(result)


# --------------------------------------------------------------------------- #
# Numbering series and settings
# --------------------------------------------------------------------------- #
@router.get("/numbering", summary="Numbering series")
def list_numbering(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.number_sequence.view")
    rows = db.execute(
        select(NumberSequence).where(NumberSequence.company_id == current.company_id).order_by(NumberSequence.document_type)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/numbering", status_code=201, summary="Configure the numbering series of a document type")
def configure_numbering(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.number_sequence.create")
    document_type = payload.get("document_type")
    if not document_type:
        raise ValidationFailure("document_type is required")
    service = NumberingService(db, current.company_id)
    row = service.configure(
        document_type,
        prefix=payload.get("prefix"),
        suffix=payload.get("suffix"),
        padding=int(payload.get("padding") if payload.get("padding") is not None else 5),
        branch_id=_uuid(payload.get("branch_id")),
        reset_yearly=bool(payload.get("reset_yearly", False)),
    )
    if payload.get("start_from") is not None:
        row.next_number = int(payload["start_from"])
    db.flush()
    return serialise(row)


@router.get("/numbering/{document_type}/peek", summary="Next document number without consuming it")
def peek_number(
    document_type: str, db: DB, current: CurrentUserDep, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    current.require("core.number_sequence.view")
    service = NumberingService(db, current.company_id)
    return {"document_type": document_type, "next": service.peek_next(document_type, branch_id=branch_id)}


@router.get("/settings", summary="Effective settings")
def list_settings(
    db: DB, current: CurrentUserDep, category: str | None = None, keys: str | None = None
) -> dict[str, Any]:
    current.require("core.system_setting.view")
    stmt = select(SystemSetting).where(
        (SystemSetting.company_id == current.company_id) | (SystemSetting.company_id.is_(None))
    )
    if category:
        stmt = stmt.where(SystemSetting.category == category)
    if keys:
        wanted = [part.strip() for part in keys.split(",") if part.strip()]
        stmt = stmt.where(SystemSetting.key.in_(wanted))
    rows = db.execute(stmt.order_by(SystemSetting.key)).scalars().all()
    values: dict[str, Any] = {}
    for row in rows:
        values[row.key] = row.value_json if row.value_json is not None else row.value
    return {"items": [serialise(row) for row in rows], "values": values, "total": len(rows)}


@router.put("/settings", summary="Set one or many settings")
def upsert_settings(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.system_setting.edit")
    rows = payload.get("settings") if "settings" in payload else payload
    if not isinstance(rows, dict):
        raise ValidationFailure("Provide an object of key/value pairs or a settings object")
    saved = []
    for key, value in rows.items():
        row = db.execute(
            select(SystemSetting).where(
                SystemSetting.company_id == current.company_id, SystemSetting.key == key
            )
        ).scalar_one_or_none()
        if row is None:
            row = SystemSetting(
                company_id=current.company_id, key=key, category=payload.get("category") or "general"
            )
            db.add(row)
        if isinstance(value, (dict, list, int, float, bool)) or value is None:
            row.value_json = value
            row.value = str(value)
        else:
            row.value = str(value)
            row.value_json = {"value": value}
        saved.append(key)
    db.flush()
    return {"saved": saved, "count": len(saved)}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="document-types",
            model=DocumentType,
            module="core",
            entity="document_type",
            search_fields=["code", "name", "module"],
            label_field="name",
            filters={"module": "module"},
            soft_delete=False,
            create_handler=guarded_create(DocumentType, unique=[("code", "Document type code")]),
        ),
        tags=["master-data"],
    ),
    prefix="/document-types",
)

# --------------------------------------------------------------------------- #
# Lookup helper for UI dropdowns
# --------------------------------------------------------------------------- #
LOOKUPS: dict[str, tuple[type[Any], str]] = {
    "currencies": (Currency, "code"),
    "countries": (Country, "name"),
    "cities": (City, "name"),
    "taxes": (Tax, "name"),
    "payment-terms": (PaymentTerm, "name"),
    "units": (UnitOfMeasure, "name"),
    "branches": (Branch, "name"),
    "departments": (Department, "name"),
    "cost-centers": (CostCenter, "name"),
}


@router.get("/lookups/{name}", summary="Lightweight options for dropdowns")
def lookup(
    name: str, db: DB, current: CurrentUserDep, q: str | None = None, limit: int = Query(50, ge=1, le=500)
) -> dict[str, Any]:
    # Dropdown data is tenant scoped and non-sensitive: any authenticated user of
    # the company may read it, but never data from another tenant.
    entry = LOOKUPS.get(name)
    if entry is None:
        raise NotFoundError("Unknown lookup", name=name)
    model, label_attr = entry
    label = getattr(model, label_attr)
    stmt = select(model.id, label)
    if hasattr(model, "company_id"):
        stmt = stmt.where((model.company_id == current.company_id) | (model.company_id.is_(None)))
    if hasattr(model, "is_active"):
        stmt = stmt.where(model.is_active.is_(True))
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    if q:
        stmt = stmt.where(label.ilike(f"%{q}%"))
    rows = db.execute(stmt.limit(limit)).all()
    return {"items": [{"id": str(row[0]), "label": row[1]} for row in rows], "total": len(rows)}


@router.get("/structure", summary="Company tree: branches, departments and cost centres")
def structure(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.branch.view")
    branches = db.execute(
        select(Branch).where(Branch.company_id == current.company_id, Branch.deleted_at.is_(None))
    ).scalars().all()
    departments = db.execute(
        select(Department).where(Department.company_id == current.company_id, Department.deleted_at.is_(None))
    ).scalars().all()
    return {
        "branches": [
            {
                **serialise(branch),
                "departments": [
                    serialise(department) for department in departments if department.branch_id == branch.id
                ],
            }
            for branch in branches
        ],
        "departments_without_branch": [
            serialise(department) for department in departments if department.branch_id is None
        ],
    }


def _uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


def _one_day() -> Any:
    from datetime import timedelta

    return timedelta(days=1)


def _count(rows: Any) -> int:
    return int(len(rows))


_ = (func,)

__all__ = ["router"]
