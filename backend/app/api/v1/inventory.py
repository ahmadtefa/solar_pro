"""Inventory: items, warehouses, batches/serials, stock documents and valuation."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError, ValidationFailure
from app.models.inventory import (
    Batch,
    ReorderRule,
    SerialNumber,
    StockBalance,
    StockLedgerEntry,
)
from app.models.masterdata import PriceList, PriceListItem, Product, ProductBarcode, ProductUnit, Warehouse
from app.schemas.masterdata import ProductCreate, WarehouseCreate
from app.services.audit_service import AuditService
from app.services.inventory_service import InventoryService
from app.services.stock_operations_service import (
    StockAdjustmentService,
    StockCountService,
    StockTransferService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Item master
# --------------------------------------------------------------------------- #
@router.get("/products", summary="List items with stock and pricing")
def list_products(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    product_type: str | None = None,
    category_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    low_stock: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("inventory.product.view")
    stmt = select(Product).where(Product.company_id == current.company_id, Product.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Product.name.ilike(f"%{q}%")
            | Product.name_ar.ilike(f"%{q}%")
            | Product.sku.ilike(f"%{q}%")
            | Product.barcode.ilike(f"%{q}%")
        )
    if product_type:
        stmt = stmt.where(Product.product_type == product_type)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    products = db.execute(
        stmt.order_by(Product.name).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    inventory = InventoryService(db, current.company_id)
    items: list[dict[str, Any]] = []
    for product in products:
        payload = serialise(product)
        if product.track_inventory:
            payload["stock_on_hand"] = str(inventory.stock_on_hand(product.id, warehouse_id))
            payload["available"] = str(inventory.available_quantity(product.id, warehouse_id))
            payload["average_cost"] = str(inventory.average_cost(product.id, warehouse_id))
            payload["stock_value"] = str(inventory.stock_value(product.id, warehouse_id))
        items.append(payload)
    if low_stock:
        items = [
            item
            for item in items
            if item.get("reorder_level")
            and Decimal(item.get("stock_on_hand", "0")) <= Decimal(str(item["reorder_level"]))
        ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/products", status_code=201, summary="Create an item")
def create_product(payload: ProductCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.product.create")
    from app.services.masterdata_service import ProductService

    product = ProductService(db, current.company_id, user_id=current.id).create(payload.data())
    AuditService(db, audit_context(current)).log_create(product, entity_type="product", label=product.sku)
    return serialise(product)


@router.get("/products/{product_id}", summary="Item master data with units and barcodes")
def get_product(product_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.product.view")
    product = db.get(Product, product_id)
    if product is None or product.company_id != current.company_id:
        raise NotFoundError("Item not found", id=str(product_id))
    payload = serialise(product)
    payload["barcodes"] = [serialise(row) for row in product.barcodes]
    payload["units"] = [serialise(row) for row in product.units]
    payload["balances"] = [
        serialise(row)
        for row in db.execute(
            select(StockBalance).where(
                StockBalance.company_id == current.company_id, StockBalance.product_id == product_id
            )
        ).scalars().all()
    ]
    return payload


@router.patch("/products/{product_id}", summary="Update an item")
def update_product(product_id: uuid.UUID, payload: ProductCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.product.edit")
    from app.services.masterdata_service import ProductService

    product = ProductService(db, current.company_id, user_id=current.id).update(product_id, payload.data())
    return serialise(product)


@router.get("/products/{product_id}/barcode", summary="Barcode lookup for POS and scanning")
def barcode_lookup(
    product_id: uuid.UUID, db: DB, current: CurrentUserDep, code: str = Query(...)
) -> dict[str, Any]:
    current.require("inventory.product.view")
    row = db.execute(
        select(ProductBarcode).where(
            ProductBarcode.company_id == current.company_id,
            ProductBarcode.barcode == code.strip(),
        )
    ).scalars().first()
    if row is None:
        product = db.execute(
            select(Product).where(
                Product.company_id == current.company_id, Product.barcode == code.strip()
            )
        ).scalars().first()
        if product is None:
            raise NotFoundError(f"No item carries barcode {code}")
        return serialise(product)
    return {"product_id": str(row.product_id), "barcode": row.barcode, "pack_quantity": str(row.pack_quantity or 1)}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="product-barcodes",
            model=ProductBarcode,
            module="inventory",
            entity="product_barcode",
            search_fields=["barcode"],
            filters={"product_id": "product_id"},
            soft_delete=False,
            create_handler=guarded_create(ProductBarcode, unique=[("barcode", "Barcode")]),
        ),
        tags=["inventory"],
    ),
    prefix="/product-barcodes",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="product-units",
            model=ProductUnit,
            module="inventory",
            entity="product_unit",
            search_fields=["barcode"],
            filters={"product_id": "product_id"},
            soft_delete=False,
        ),
        tags=["inventory"],
    ),
    prefix="/product-units",
)


@router.put("/products/{product_id}/units", summary="Replace the unit conversions of an item")
def set_product_units(
    product_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: list[dict[str, Any]] = Body(...)
) -> dict[str, Any]:
    current.require("inventory.product_unit.create")
    from app.services.masterdata_service import ProductService

    rows = ProductService(db, current.company_id, user_id=current.id).set_units(product_id, payload)
    return {"product_id": str(product_id), "units": [serialise(row) for row in rows]}


@router.get("/products/{product_id}/stock", summary="Stock position of one item per warehouse")
def product_stock(
    product_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    warehouse_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("inventory.stock_balance.view")
    inventory = InventoryService(db, current.company_id)
    stmt = select(StockBalance).where(
        StockBalance.company_id == current.company_id, StockBalance.product_id == product_id
    )
    if warehouse_id:
        stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
    rows = db.execute(stmt).scalars().all()
    return {
        "product_id": str(product_id),
        "on_hand": str(inventory.stock_on_hand(product_id, warehouse_id)),
        "available": str(inventory.available_quantity(product_id, warehouse_id)),
        "value": str(inventory.stock_value(product_id, warehouse_id)),
        "average_cost": str(inventory.average_cost(product_id, warehouse_id)),
        "balances": [serialise(row) for row in rows],
    }


# --------------------------------------------------------------------------- #
# Warehouses
# --------------------------------------------------------------------------- #
@router.get("/warehouses", summary="Warehouses of the company")
def list_warehouses(db: DB, current: CurrentUserDep, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    current.require("inventory.warehouse.view")
    stmt = select(Warehouse).where(Warehouse.company_id == current.company_id, Warehouse.deleted_at.is_(None))
    if branch_id:
        stmt = stmt.where(Warehouse.branch_id == branch_id)
    rows = db.execute(stmt.order_by(Warehouse.code)).scalars().all()
    items = []
    for row in rows:
        payload = serialise(row)
        payload["stock_value"] = str(
            db.execute(
                select(func.coalesce(func.sum(StockBalance.total_value), 0)).where(
                    StockBalance.company_id == current.company_id, StockBalance.warehouse_id == row.id
                )
            ).scalar_one()
        )
        payload["item_count"] = int(
            db.execute(
                select(func.count()).select_from(StockBalance).where(
                    StockBalance.company_id == current.company_id,
                    StockBalance.warehouse_id == row.id,
                    StockBalance.quantity != 0,
                )
            ).scalar_one()
        )
        items.append(payload)
    return {"items": items, "total": len(items)}


@router.post("/warehouses", status_code=201, summary="Create a warehouse")
def create_warehouse(payload: WarehouseCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.warehouse.create")
    data = payload.data()
    data.setdefault("company_id", current.company_id)
    warehouse = Warehouse(**{key: value for key, value in data.items() if hasattr(Warehouse, key)})
    db.add(warehouse)
    db.flush()
    AuditService(db, audit_context(current)).log_create(warehouse, entity_type="warehouse", label=warehouse.code)
    return serialise(warehouse)


# --------------------------------------------------------------------------- #
# Ledger, balances, valuation
# --------------------------------------------------------------------------- #
@router.get("/stock/ledger", summary="Immutable stock ledger entries")
def stock_ledger(
    db: DB,
    current: CurrentUserDep,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    include_reversed: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    current.require("inventory.stock_ledger.view")
    stmt = select(StockLedgerEntry).where(StockLedgerEntry.company_id == current.company_id)
    if product_id:
        stmt = stmt.where(StockLedgerEntry.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockLedgerEntry.warehouse_id == warehouse_id)
    if reference_type:
        stmt = stmt.where(StockLedgerEntry.reference_type == reference_type)
    if reference_id:
        stmt = stmt.where(StockLedgerEntry.reference_id == reference_id)
    if not include_reversed:
        stmt = stmt.where(StockLedgerEntry.is_reversed.is_(False))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(StockLedgerEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/stock/balances", summary="Stock balances per item/warehouse/batch")
def stock_balances(
    db: DB,
    current: CurrentUserDep,
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    only_non_zero: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    current.require("inventory.stock_balance.view")
    stmt = select(StockBalance).where(StockBalance.company_id == current.company_id)
    if warehouse_id:
        stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
    if product_id:
        stmt = stmt.where(StockBalance.product_id == product_id)
    if only_non_zero:
        stmt = stmt.where(StockBalance.quantity != 0)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(StockBalance.product_id).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/stock/low-stock", summary="Items at or below their reorder level")
def low_stock(
    db: DB, current: CurrentUserDep, warehouse_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    current.require("inventory.reorder_rule.view")
    items = InventoryService(db, current.company_id).low_stock_items(warehouse_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/stock/reconcile", summary="Compare stock balances with the ledger (admin check)")
def reconcile(db: DB, current: CurrentUserDep, product_id: uuid.UUID | None = None) -> dict[str, Any]:
    current.require("inventory.inventory_valuation.view")
    discrepancies = InventoryService(db, current.company_id).reconcile_balances(product_id)
    return {"discrepancies": discrepancies, "balanced": not discrepancies}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="batches",
            model=Batch,
            module="inventory",
            entity="batch",
            search_fields=["batch_number", "supplier_batch_no"],
            default_sort="created_at",
            filters={"product_id": "product_id", "warehouse_id": "warehouse_id"},
            create_handler=guarded_create(Batch),
        ),
        tags=["inventory"],
    ),
    prefix="/batches",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="serials",
            model=SerialNumber,
            module="inventory",
            entity="serial",
            search_fields=["serial_number"],
            filters={"product_id": "product_id", "status": "status"},
            create_handler=guarded_create(SerialNumber),
        ),
        tags=["inventory"],
    ),
    prefix="/serials",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="price-lists",
            model=PriceList,
            module="inventory",
            entity="price_list",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(PriceList, unique=[("code", "Price list code")]),
        ),
        tags=["inventory"],
    ),
    prefix="/price-lists",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="reorder-rules",
            model=ReorderRule,
            module="inventory",
            entity="reorder_rule",
            filters={"product_id": "product_id", "warehouse_id": "warehouse_id"},
            create_handler=guarded_create(ReorderRule),
        ),
        tags=["inventory"],
    ),
    prefix="/reorder-rules",
)


@router.get("/price-lists/{price_list_id}/items", summary="Prices of a price list")
def price_list_items(price_list_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.price_list.view")
    rows = db.execute(
        select(PriceListItem).where(
            PriceListItem.company_id == current.company_id, PriceListItem.price_list_id == price_list_id
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@router.put("/price-lists/{price_list_id}/items", summary="Replace the prices of a price list")
def set_price_list_items(
    price_list_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: list[dict[str, Any]] = Body(...)
) -> dict[str, Any]:
    current.require("inventory.price_list.edit")
    existing = db.execute(
        select(PriceListItem).where(
            PriceListItem.company_id == current.company_id, PriceListItem.price_list_id == price_list_id
        )
    ).scalars().all()
    for row in existing:
        db.delete(row)
    created = 0
    for entry in payload:
        product_id = entry.get("product_id")
        if not product_id:
            raise ValidationFailure("Every price row needs a product_id")
        db.add(
            PriceListItem(
                company_id=current.company_id,
                price_list_id=price_list_id,
                product_id=uuid.UUID(str(product_id)),
                unit_id=uuid.UUID(str(entry["unit_id"])) if entry.get("unit_id") else None,
                min_quantity=Decimal(str(entry.get("min_quantity", 1))),
                price=Decimal(str(entry.get("price", 0))),
                discount_percent=Decimal(str(entry.get("discount_percent", 0))),
            )
        )
        created += 1
    db.flush()
    return {"price_list_id": str(price_list_id), "items": created}


# --------------------------------------------------------------------------- #
# Stock documents
# --------------------------------------------------------------------------- #
router.include_router(
    build_document_router(
        DocumentSpec(
            name="stock-transfers",
            service=StockTransferService,
            label="stock transfers",
            tag="inventory",
            date_field="transfer_date",
            search_fields=("document_no",),
        )
    ),
    prefix="/stock-transfers",
)

moves_router = build_document_router(
    DocumentSpec(
        name="stock-adjustments",
        service=StockAdjustmentService,
        label="stock adjustments",
        tag="inventory",
        date_field="adjustment_date",
        search_fields=("document_no",),
    )
)


@moves_router.get("/availability/{warehouse_id}", summary="Items available in a warehouse (for transfers)")
def transfer_availability(
    warehouse_id: uuid.UUID, db: DB, current: CurrentUserDep, product_ids: str | None = None
) -> dict[str, Any]:
    current.require("inventory.stock_balance.view")
    ids = [uuid.UUID(item) for item in product_ids.split(",")] if product_ids else None
    service = StockTransferService(db, current.company_id, user_id=current.id)
    return {"items": service.availability(warehouse_id=warehouse_id, product_ids=ids)}


router.include_router(moves_router, prefix="/stock-adjustments")

counts_router = build_document_router(
    DocumentSpec(
        name="stock-counts",
        service=StockCountService,
        label="stock counts",
        tag="inventory",
        date_field="count_date",
        search_fields=("document_no",),
    )
)


@counts_router.post("/{document_id}/record", summary="Record the counted quantities")
def record_counts(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: list[dict[str, Any]] = Body(...)
) -> dict[str, Any]:
    current.require("inventory.stock_count.edit")
    service = StockCountService(db, current.company_id, user_id=current.id)
    document = service.get_document(document_id)
    service.record_counts(document, payload)
    db.flush()
    return {**serialise(document), "lines": [serialise(line) for line in document.lines]}


router.include_router(counts_router, prefix="/stock-counts")

__all__ = ["router"]
