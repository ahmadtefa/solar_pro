"""Fixed assets: categories, register, acquisition, depreciation, transfer, disposal."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError
from app.models.assets import (
    Asset,
    AssetCategory,
    AssetDepreciation,
    AssetDisposal,
    AssetMaintenance,
    AssetTransfer,
)
from app.services.asset_service import AssetCategoryService, AssetService, DepreciationService
from app.services.audit_service import AuditService

router = APIRouter()

# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@router.get("/categories", summary="Asset categories and their depreciation policy")
def list_categories(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_category.view")
    rows = AssetCategoryService(db, current.company_id).list()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/categories", status_code=201, summary="Create an asset category")
def create_category(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_category.create")
    category = AssetCategoryService(db, current.company_id, user_id=current.id).create(payload)
    AuditService(db, audit_context(current)).log_create(
        category, entity_type="asset_category", label=category.code
    )
    return serialise(category)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="asset-categories",
            model=AssetCategory,
            module="assets",
            entity="asset_category",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(AssetCategory, unique=[("code", "Category code")]),
        ),
        tags=["assets"],
    ),
    prefix="/asset-categories",
)

# --------------------------------------------------------------------------- #
# Register
# --------------------------------------------------------------------------- #
@router.get("/register", summary="Asset register with book values")
def register(
    db: DB,
    current: CurrentUserDep,
    branch_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    current.require("assets.asset.view")
    report = DepreciationService(db, current.company_id).register(branch_id=branch_id, category_id=category_id)
    items = report["assets"]
    if status_filter:
        items = [row for row in items if row.get("status") == status_filter]
    return {"items": items, "total": len(items), "totals": report["totals"]}


@router.get("/assets", summary="Assets")
def list_assets(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    category_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("assets.asset.view")
    stmt = select(Asset).where(Asset.company_id == current.company_id, Asset.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Asset.name.ilike(f"%{q}%") | Asset.asset_no.ilike(f"%{q}%") | Asset.serial_number.ilike(f"%{q}%")
        )
    if category_id:
        stmt = stmt.where(Asset.category_id == category_id)
    if branch_id:
        stmt = stmt.where(Asset.branch_id == branch_id)
    if department_id:
        stmt = stmt.where(Asset.department_id == department_id)
    if status_filter:
        stmt = stmt.where(Asset.status == status_filter)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Asset.asset_no).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/assets", status_code=201, summary="Acquire an asset (creates the fixed-asset document)")
def acquire_asset(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset.create")
    asset = AssetService(db, current.company_id, user_id=current.id).acquire(payload)
    db.flush()
    return serialise(asset)


@router.get("/assets/{asset_id}", summary="Asset 360: costs, depreciation, maintenance")
def get_asset(asset_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset.view")
    service = AssetService(db, current.company_id, user_id=current.id)
    asset = service.get(asset_id)
    payload = serialise(asset)
    payload["depreciations"] = [
        serialise(row)
        for row in db.execute(
            select(AssetDepreciation)
            .where(
                AssetDepreciation.company_id == current.company_id,
                AssetDepreciation.asset_id == asset_id,
            )
            .order_by(AssetDepreciation.depreciation_date.desc())
        ).scalars().all()
    ]
    payload["maintenance"] = [serialise(row) for row in service.maintenance_history(asset_id)]
    payload["transfers"] = [
        serialise(row)
        for row in db.execute(
            select(AssetTransfer).where(
                AssetTransfer.company_id == current.company_id, AssetTransfer.asset_id == asset_id
            )
        ).scalars().all()
    ]
    payload["disposals"] = [
        serialise(row)
        for row in db.execute(
            select(AssetDisposal).where(
                AssetDisposal.company_id == current.company_id, AssetDisposal.asset_id == asset_id
            )
        ).scalars().all()
    ]
    return payload


@router.post("/assets/{asset_id}/capitalize", summary="Capitalize (activate) an acquired asset")
def capitalize_asset(
    asset_id: uuid.UUID, db: DB, current: CurrentUserDep, posting: bool = True
) -> dict[str, Any]:
    current.require("assets.asset.edit")
    asset = AssetService(db, current.company_id, user_id=current.id).capitalize(asset_id, posting=posting)
    db.flush()
    return serialise(asset)


@router.post("/assets/{asset_id}/costs", summary="Add a capitalizable cost to an asset")
def add_asset_cost(asset_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset.edit")
    asset = AssetService(db, current.company_id, user_id=current.id).add_cost(
        asset_id,
        amount=Decimal(str(payload.get("amount", 0))),
        description=payload.get("description"),
    )
    db.flush()
    return serialise(asset)


@router.post("/assets/{asset_id}/transfer", summary="Transfer an asset between branches/custodians")
def transfer_asset(asset_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_transfer.create")
    transfer = AssetService(db, current.company_id, user_id=current.id).transfer(asset_id, payload)
    db.flush()
    return serialise(transfer)


@router.post("/assets/{asset_id}/dispose", summary="Dispose of an asset (with gain/loss posting)")
def dispose_asset(asset_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_disposal.create")
    disposal = AssetService(db, current.company_id, user_id=current.id).dispose(asset_id, payload)
    db.flush()
    return serialise(disposal)


@router.post("/disposals/{disposal_id}/approve", summary="Approve a disposal")
def approve_disposal(disposal_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_disposal.approve")
    disposal = AssetService(db, current.company_id, user_id=current.id).approve_disposal(disposal_id)
    db.flush()
    return serialise(disposal)


@router.post("/assets/{asset_id}/maintenance", summary="Record maintenance for an asset")
def record_maintenance(
    asset_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("assets.asset_maintenance.create")
    record = AssetService(db, current.company_id, user_id=current.id).record_maintenance(asset_id, payload)
    db.flush()
    return serialise(record)


@router.get("/assets/{asset_id}/maintenance", summary="Maintenance history")
def maintenance_history(asset_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset_maintenance.view")
    rows = AssetService(db, current.company_id, user_id=current.id).maintenance_history(asset_id)
    return {"items": [serialise(row) for row in rows]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="maintenance",
            model=AssetMaintenance,
            module="assets",
            entity="asset_maintenance",
            search_fields=["document_no", "description", "performed_by"],
            default_sort="reported_date",
            filters={"asset_id": "asset_id", "status": "status"},
            create_handler=guarded_create(AssetMaintenance),
        ),
        tags=["assets"],
    ),
    prefix="/asset-maintenance",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="transfers",
            model=AssetTransfer,
            module="assets",
            entity="asset_transfer",
            search_fields=["document_no"],
            default_sort="transfer_date",
            filters={"asset_id": "asset_id", "status": "status"},
            create_handler=guarded_create(AssetTransfer),
        ),
        tags=["assets"],
    ),
    prefix="/asset-transfers",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="disposals",
            model=AssetDisposal,
            module="assets",
            entity="asset_disposal",
            search_fields=["document_no", "buyer_name"],
            default_sort="disposal_date",
            filters={"asset_id": "asset_id", "status": "status"},
            create_handler=guarded_create(AssetDisposal),
        ),
        tags=["assets"],
    ),
    prefix="/asset-disposals",
)

# --------------------------------------------------------------------------- #
# Depreciation
# --------------------------------------------------------------------------- #
@router.post("/depreciation/run", summary="Run monthly depreciation")
def run_depreciation(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.depreciation.create")
    service = DepreciationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    result = service.run(
        period_year=int(payload.get("period_year") or date.today().year),
        period_month=int(payload.get("period_month") or date.today().month),
        branch_id=uuid.UUID(str(payload["branch_id"])) if payload.get("branch_id") else None,
        asset_ids=[uuid.UUID(str(item)) for item in payload.get("asset_ids") or []]
        or None,
        post=bool(payload.get("post", True)),
        units_produced=payload.get("units_produced"),
    )
    db.flush()
    if isinstance(result, dict):
        return result
    return serialise(result)


@router.get("/depreciation/schedule/{asset_id}", summary="Projected depreciation schedule of an asset")
def depreciation_schedule(
    asset_id: uuid.UUID, db: DB, current: CurrentUserDep, periods: int = Query(12, ge=1, le=600)
) -> dict[str, Any]:
    current.require("assets.depreciation.view")
    rows = DepreciationService(db, current.company_id).schedule(asset_id, periods=periods)
    return {"items": rows, "total": len(rows)}


@router.get("/depreciation", summary="Posted depreciation entries")
def list_depreciation(
    db: DB,
    current: CurrentUserDep,
    asset_id: uuid.UUID | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    current.require("assets.depreciation.view")
    stmt = select(AssetDepreciation).where(AssetDepreciation.company_id == current.company_id)
    if asset_id:
        stmt = stmt.where(AssetDepreciation.asset_id == asset_id)
    if period_year:
        stmt = stmt.where(AssetDepreciation.period_year == period_year)
    if period_month:
        stmt = stmt.where(AssetDepreciation.period_month == period_month)
    rows = db.execute(
        stmt.order_by(AssetDepreciation.depreciation_date.desc()).limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.get("/reports/summary", summary="Asset movement summary")
def asset_summary(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("assets.asset.view")
    report = DepreciationService(db, current.company_id).register()
    by_status: dict[str, dict[str, Decimal]] = {}
    for row in report["assets"]:
        key = row.get("status") or "unknown"
        bucket = by_status.setdefault(key, {"cost": Decimal("0"), "book": Decimal("0"), "count": Decimal("0")})
        bucket["cost"] += Decimal(str(row.get("total_cost") or 0))
        bucket["book"] += Decimal(str(row.get("book_value") or 0))
        bucket["count"] += 1
    return {
        "items": [
            {
                "status": status,
                "assets": int(values["count"]),
                "cost": str(values["cost"]),
                "book_value": str(values["book"]),
                "accumulated": str(values["cost"] - values["book"]),
            }
            for status, values in by_status.items()
        ],
        "totals": report["totals"],
        "total_assets": report["count"],
    }


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = (NotFoundError,)

__all__ = ["router"]
