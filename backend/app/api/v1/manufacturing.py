"""Manufacturing: work centres, BOMs, routings, production orders and WIP costing."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError, ValidationFailure
from app.models.manufacturing import (
    Bom,
    BomLine,
    BomOperation,
    ProductionOperation,
    ProductionOrder,
    ProductionOrderMaterial,
    ProductionOutput,
    Routing,
    RoutingOperation,
    WorkCenter,
)
from app.services.audit_service import AuditService
from app.services.manufacturing_service import (
    BomService,
    ProductionOrderService,
    RoutingService,
    WorkCenterService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Master data
# --------------------------------------------------------------------------- #
@router.get("/work-centers", summary="Work centres with capacity")
def list_work_centers(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.work_center.view")
    rows = WorkCenterService(db, current.company_id).list()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/work-centers", status_code=201, summary="Create a work centre")
def create_work_center(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.work_center.create")
    center = WorkCenterService(db, current.company_id, user_id=current.id).create(payload)
    AuditService(db, audit_context(current)).log_create(center, entity_type="work_center", label=center.code)
    return serialise(center)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="work-centers",
            model=WorkCenter,
            module="manufacturing",
            entity="work_center",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(WorkCenter, unique=[("code", "Work centre code")]),
        ),
        tags=["manufacturing"],
    ),
    prefix="/work-center-master",
)

# --------------------------------------------------------------------------- #
# Bills of materials
# --------------------------------------------------------------------------- #
@router.get("/boms", summary="Bills of materials")
def list_boms(
    db: DB,
    current: CurrentUserDep,
    product_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("manufacturing.bom.view")
    stmt = select(Bom).where(Bom.company_id == current.company_id, Bom.deleted_at.is_(None))
    if product_id:
        stmt = stmt.where(Bom.product_id == product_id)
    if active_only:
        stmt = stmt.where(Bom.is_active.is_(True))
    rows = db.execute(stmt.order_by(Bom.code).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/boms", status_code=201, summary="Create a BOM with components and operations")
def create_bom(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.bom.create")
    bom = BomService(db, current.company_id, user_id=current.id).create_bom(payload)
    return {
        **serialise(bom),
        "components": [serialise(line) for line in bom.components],
        "operations": [serialise(line) for line in bom.operations],
    }


@router.get("/boms/{bom_id}", summary="BOM detail with standard cost")
def get_bom(bom_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.bom.view")
    service = BomService(db, current.company_id, user_id=current.id)
    bom = service.get(bom_id)
    return {
        **serialise(bom),
        "components": [serialise(line) for line in bom.components],
        "operations": [serialise(line) for line in bom.operations],
        "standard_cost": str(service.compute_standard_cost(bom)),
    }


@router.put("/boms/{bom_id}/components", summary="Replace the components of a BOM")
def set_bom_components(
    bom_id: uuid.UUID, payload: list[dict[str, Any]], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("manufacturing.bom.edit")
    service = BomService(db, current.company_id, user_id=current.id)
    bom = service.get(bom_id)
    service.set_lines(bom, payload)
    return {"bom_id": str(bom.id), "components": len(bom.components)}


@router.put("/boms/{bom_id}/operations", summary="Replace the operations of a BOM")
def set_bom_operations(
    bom_id: uuid.UUID, payload: list[dict[str, Any]], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("manufacturing.bom.edit")
    service = BomService(db, current.company_id, user_id=current.id)
    bom = service.get(bom_id)
    service.set_operations(bom, payload)
    return {"bom_id": str(bom.id), "operations": len(bom.operations)}


@router.get("/boms/{bom_id}/explode", summary="Multi-level explosion of a BOM")
def explode_bom(
    bom_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    quantity_value: str = Query("1"),
    depth: int = Query(0, ge=0, le=10),
) -> dict[str, Any]:
    current.require("manufacturing.bom.view")
    service = BomService(db, current.company_id, user_id=current.id)
    bom = service.get(bom_id)
    rows = service.explode(bom.product_id, quantity_value=Decimal(quantity_value), depth=depth)
    return {"items": rows, "total": len(rows)}


@router.post("/boms/{bom_id}/clone", status_code=201, summary="Clone a BOM into a new version")
def clone_bom(bom_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.bom.create")
    clone = BomService(db, current.company_id, user_id=current.id).clone_version(bom_id)
    return serialise(clone)


@router.get("/boms/active/{product_id}", summary="Active BOM of a finished good")
def active_bom(product_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.bom.view")
    bom = BomService(db, current.company_id, user_id=current.id).active_bom(product_id)
    if bom is None:
        raise NotFoundError("No active BOM for this product", product_id=str(product_id))
    return {**serialise(bom), "components": [serialise(line) for line in bom.components]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="components",
            model=BomLine,
            module="manufacturing",
            entity="bom",
            filters={"bom_id": "bom_id", "component_product_id": "component_product_id"},
            soft_delete=False,
            create_handler=guarded_create(BomLine),
        ),
        tags=["manufacturing"],
    ),
    prefix="/bom-components",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="bom-operations",
            model=BomOperation,
            module="manufacturing",
            entity="bom",
            filters={"bom_id": "bom_id"},
            soft_delete=False,
            create_handler=guarded_create(BomOperation),
        ),
        tags=["manufacturing"],
    ),
    prefix="/bom-operations",
)

# --------------------------------------------------------------------------- #
# Routings
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="routings",
            model=Routing,
            module="manufacturing",
            entity="routing",
            search_fields=["code", "name"],
            label_field="name",
            filters={"product_id": "product_id"},
            create_handler=guarded_create(Routing, unique=[("code", "Routing code")]),
        ),
        tags=["manufacturing"],
    ),
    prefix="/routings",
)


@router.post("/routings", status_code=201, summary="Create a routing with its operations")
def create_routing(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.routing.create")
    routing = RoutingService(db, current.company_id, user_id=current.id).create(payload)
    return {**serialise(routing), "operations": [serialise(row) for row in routing.operations]}


@router.get("/routings/{routing_id}", summary="Routing with operations")
def get_routing(routing_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.routing.view")
    routing = db.get(Routing, routing_id)
    if routing is None or routing.company_id != current.company_id:
        raise NotFoundError("Routing not found", id=str(routing_id))
    return {**serialise(routing), "operations": [serialise(row) for row in routing.operations]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="routing-operations",
            model=RoutingOperation,
            module="manufacturing",
            entity="routing",
            filters={"routing_id": "routing_id"},
            soft_delete=False,
            create_handler=guarded_create(RoutingOperation),
        ),
        tags=["manufacturing"],
    ),
    prefix="/routing-operations",
)

# --------------------------------------------------------------------------- #
# Production orders
# --------------------------------------------------------------------------- #
production_router = build_document_router(
    DocumentSpec(
        name="production-orders",
        service=ProductionOrderService,
        label="production orders",
        tag="manufacturing",
        party_field="sales_order_id",
        search_fields=("document_no", "reference"),
        extra_actions={
            "issue-materials": "issue_materials",
            "produce": "produce",
            "record-operation": "record_operation",
            "close": "close",
            "variance": "analyze_variance",
        },
    )
)


@production_router.post("/{document_id}/plan", summary="Plan a production order")
def plan_order(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_order.edit")
    service = ProductionOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.plan(document_id)
    db.flush()
    return {**serialise(order), "materials": [serialise(row) for row in order.materials]}


@production_router.post("/{document_id}/release", summary="Release a plan to the shop floor")
def release_order(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_order.approve")
    service = ProductionOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.release(document_id)
    db.flush()
    return serialise(order)


@production_router.get("/{document_id}/materials", summary="Material requirements and issues")
def order_materials(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_order.view")
    order = db.get(ProductionOrder, document_id)
    if order is None or order.company_id != current.company_id:
        raise NotFoundError("Production order not found", id=str(document_id))
    return {"items": [serialise(row) for row in order.materials]}


@production_router.get("/{document_id}/operations", summary="Routing operations of the order")
def order_operations(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_order.view")
    order = db.get(ProductionOrder, document_id)
    if order is None or order.company_id != current.company_id:
        raise NotFoundError("Production order not found", id=str(document_id))
    return {"items": [serialise(row) for row in order.operations]}


@production_router.get("/{document_id}/outputs", summary="Finished goods produced so far")
def order_outputs(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_output.view")
    rows = db.execute(
        select(ProductionOutput).where(
            ProductionOutput.company_id == current.company_id,
            ProductionOutput.production_order_id == document_id,
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@production_router.get("/{document_id}/wip", summary="WIP position of the order")
def order_wip(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.production_order.view")
    service = ProductionOrderService(db, current.company_id, user_id=current.id)
    order = service.get_document(document_id) if hasattr(service, "get_document") else db.get(ProductionOrder, document_id)
    variance = service.analyze_variance(order.id)
    return variance if isinstance(variance, dict) else serialise(order)


router.include_router(production_router, prefix="/production-orders")


@router.get("/production/board", summary="Shop floor board: open orders with progress")
def production_board(db: DB, current: CurrentUserDep, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    current.require("manufacturing.production_order.view")
    rows = db.execute(
        select(ProductionOrder)
        .where(
            ProductionOrder.company_id == current.company_id,
            ProductionOrder.status.in_(["draft", "planned", "released", "in_progress"]),
        )
        .order_by(ProductionOrder.planned_start_date.asc().nulls_last())
        .limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                **serialise(order),
                "material_count": len(order.materials),
                "operation_count": len(order.operations),
            }
            for order in rows
        ],
        "total": len(rows),
    }


@router.get("/scrap", summary="Scrap and rework recorded against production orders")
def list_scrap(
    db: DB,
    current: CurrentUserDep,
    production_order_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("manufacturing.production_output.view")
    stmt = select(ProductionOutput).where(
        ProductionOutput.company_id == current.company_id,
        ProductionOutput.output_type.in_(["scrap", "rework"]),
    )
    if production_order_id:
        stmt = stmt.where(ProductionOutput.production_order_id == production_order_id)
    if product_id:
        stmt = stmt.where(ProductionOutput.product_id == product_id)
    if date_from:
        stmt = stmt.where(ProductionOutput.produced_at >= date_from)
    if date_to:
        stmt = stmt.where(ProductionOutput.produced_at <= date_to)
    rows = db.execute(stmt.order_by(ProductionOutput.produced_at.desc()).limit(limit)).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": len(rows),
        "value": str(sum((row.total_cost or 0) for row in rows)),
    }


@router.post("/production-orders/{document_id}/scrap", status_code=201, summary="Record scrap for an order")
def record_scrap(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("manufacturing.production_output.create")
    if not payload.get("quantity"):
        raise ValidationFailure("quantity is required")
    service = ProductionOrderService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    record = service.produce(document_id, {**payload, "output_type": "scrap"})
    db.flush()
    return serialise(record)


@router.get("/reports/cost-variance", summary="Production cost variance per order")
def cost_variance(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("manufacturing.production_order.view")
    service = ProductionOrderService(db, current.company_id)
    stmt = select(ProductionOrder).where(
        ProductionOrder.company_id == current.company_id,
        ProductionOrder.status.in_(["completed", "cancelled"]),
    )
    if date_from:
        stmt = stmt.where(ProductionOrder.created_at >= date_from)
    if date_to:
        stmt = stmt.where(ProductionOrder.created_at <= date_to)
    rows = db.execute(stmt.order_by(ProductionOrder.created_at.desc()).limit(limit)).scalars().all()
    items = []
    for order in rows:
        variance = service.analyze_variance(order.id)
        items.append(variance if isinstance(variance, dict) else {"production_order_id": str(order.id)})
    return {"items": items, "total": len(items)}


@router.get("/reports/work-center-load", summary="Work centre load from open operations")
def work_center_load(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("manufacturing.work_center.view")
    rows = db.execute(
        select(
            WorkCenter.code,
            WorkCenter.name,
            func.count(ProductionOperation.id),
            func.coalesce(func.sum(ProductionOperation.planned_minutes), 0),
        )
        .join(ProductionOperation, ProductionOperation.work_center_id == WorkCenter.id)
        .join(ProductionOrder, ProductionOrder.id == ProductionOperation.production_order_id)
        .where(
            WorkCenter.company_id == current.company_id,
            ProductionOrder.status.in_(["draft", "planned", "released", "in_progress"]),
        )
        .group_by(WorkCenter.code, WorkCenter.name)
    ).all()
    return {
        "items": [
            {
                "work_center": row[0],
                "name": row[1],
                "operations": int(row[2]),
                "planned_minutes": str(row[3]),
            }
            for row in rows
        ]
    }


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="order-materials",
            model=ProductionOrderMaterial,
            module="manufacturing",
            entity="production_order",
            filters={"production_order_id": "production_order_id", "product_id": "product_id"},
            soft_delete=False,
        ),
        tags=["manufacturing"],
    ),
    prefix="/production-materials",
)


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = ValidationFailure

__all__ = ["router"]
