"""Purchasing: requests, RFQs, quotations, orders, receipts, invoices and returns."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError
from app.models.masterdata import (
    Contact,
    Supplier,
    SupplierGroup,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.models.purchasing import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseRequest,
    Rfq,
    SupplierEvaluation,
    SupplierQuotation,
)
from app.services.audit_service import AuditService
from app.services.purchasing_service import (
    DebitNoteService,
    GoodsReceiptService,
    PurchaseInvoiceService,
    PurchaseOrderService,
    PurchaseRequestService,
    RfqService,
    SupplierEvaluationService,
    SupplierQuotationService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Supplier master data
# --------------------------------------------------------------------------- #
@router.get("/suppliers", summary="Suppliers with balances and credit")
def list_suppliers(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    group_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("suppliers.supplier.view")
    stmt = select(Supplier).where(Supplier.company_id == current.company_id, Supplier.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Supplier.name.ilike(f"%{q}%")
            | Supplier.name_ar.ilike(f"%{q}%")
            | Supplier.code.ilike(f"%{q}%")
            | Supplier.email.ilike(f"%{q}%")
        )
    if group_id:
        stmt = stmt.where(Supplier.supplier_group_id == group_id)
    if not include_inactive:
        stmt = stmt.where(Supplier.is_active.is_(True))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    balances = _supplier_balances(db, current, [row.id for row in rows])
    return {
        "items": [{**serialise(row), "balance": str(balances.get(row.id, 0))} for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


def _supplier_balances(db: DB, current: CurrentUserDep, supplier_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    """Outstanding payable per supplier from posted invoices minus payments."""
    from app.models.purchasing import PurchaseInvoice

    if not supplier_ids:
        return {}
    rows = db.execute(
        select(
            PurchaseInvoice.supplier_id,
            func.coalesce(func.sum(PurchaseInvoice.total_amount - PurchaseInvoice.paid_amount), 0),
        )
        .where(
            PurchaseInvoice.company_id == current.company_id,
            PurchaseInvoice.supplier_id.in_(supplier_ids),
            PurchaseInvoice.status == "posted",
        )
        .group_by(PurchaseInvoice.supplier_id)
    ).all()
    return {row[0]: row[1] for row in rows}


@router.post("/suppliers", status_code=201, summary="Create a supplier")
def create_supplier(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("suppliers.supplier.create")
    from app.services.masterdata_service import PartyService

    supplier = PartyService(db, current.company_id, user_id=current.id).create_supplier(payload)
    AuditService(db, audit_context(current)).log_create(
        supplier, entity_type="supplier", label=supplier.name
    )
    return serialise(supplier)


@router.get("/suppliers/{supplier_id}", summary="Supplier 360: profile, credit, purchases and contacts")
def get_supplier(supplier_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("suppliers.supplier.view")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.company_id != current.company_id or supplier.deleted_at is not None:
        raise NotFoundError("Supplier not found", id=str(supplier_id))
    from app.models.purchasing import PurchaseInvoice, PurchaseOrder

    balances = _supplier_balances(db, current, [supplier_id])
    recent_orders = db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.company_id == current.company_id, PurchaseOrder.supplier_id == supplier_id)
        .order_by(PurchaseOrder.document_date.desc())
        .limit(10)
    ).scalars().all()
    recent_invoices = db.execute(
        select(PurchaseInvoice)
        .where(PurchaseInvoice.company_id == current.company_id, PurchaseInvoice.supplier_id == supplier_id)
        .order_by(PurchaseInvoice.document_date.desc())
        .limit(10)
    ).scalars().all()
    contacts = db.execute(
        select(Contact).where(
            Contact.company_id == current.company_id, Contact.supplier_id == supplier_id
        )
    ).scalars().all()
    return {
        **serialise(supplier),
        "balance": str(balances.get(supplier_id, 0)),
        "recent_orders": [serialise(row) for row in recent_orders],
        "recent_invoices": [serialise(row) for row in recent_invoices],
        "contacts": [serialise(row) for row in contacts],
    }


@router.patch("/suppliers/{supplier_id}", summary="Update a supplier")
def update_supplier(
    supplier_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("suppliers.supplier.edit")
    from app.services.masterdata_service import PartyService

    supplier = PartyService(db, current.company_id, user_id=current.id).update_supplier(supplier_id, payload)
    return serialise(supplier)


@router.post("/suppliers/{supplier_id}/contacts", status_code=201, summary="Add a supplier contact")
def add_supplier_contact(
    supplier_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("suppliers.supplier.edit")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.company_id != current.company_id:
        raise NotFoundError("Supplier not found", id=str(supplier_id))
    from app.services.masterdata_service import PartyService

    contact = PartyService(db, current.company_id, user_id=current.id).add_contact(
        party_type="supplier", party_id=supplier_id, payload=payload
    )
    db.flush()
    return serialise(contact)


@router.get("/supplier-groups", summary="Supplier groups")
def list_supplier_groups(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("suppliers.supplier.view")
    rows = db.execute(
        select(SupplierGroup)
        .where(SupplierGroup.company_id == current.company_id, SupplierGroup.deleted_at.is_(None))
        .order_by(SupplierGroup.name)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="supplier-groups",
            model=SupplierGroup,
            module="suppliers",
            entity="supplier",
            search_fields=["code", "name", "name_ar"],
            label_field="name",
            create_handler=guarded_create(SupplierGroup),
        ),
        tags=["suppliers"],
    ),
    prefix="/supplier-group-master",
)


# --------------------------------------------------------------------------- #
# Lifecycle resources
# --------------------------------------------------------------------------- #
requests_router = build_document_router(
    DocumentSpec(
        name="purchase-requests",
        service=PurchaseRequestService,
        label="purchase requests",
        tag="purchasing",
        party_field="requested_by_id",
    )
)


@requests_router.post("/{document_id}/rfq", summary="Raise an RFQ from an approved request")
def rfq_from_request(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("purchasing.rfq.create")
    supplier_ids = [uuid.UUID(str(item)) for item in payload.get("supplier_ids") or []]
    if not supplier_ids:
        from app.core.errors import ValidationFailure

        raise ValidationFailure("supplier_ids is required")
    service = RfqService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    rfq = service.create_from_request(document_id, supplier_ids)
    db.flush()
    return {**serialise(rfq), "supplier_ids": [str(item) for item in supplier_ids]}


router.include_router(requests_router, prefix="/purchase-requests")

router.include_router(
    build_document_router(
        DocumentSpec(name="rfqs", service=RfqService, label="RFQs", tag="purchasing", create_only=True)
    ),
    prefix="/rfqs",
)

quotes_router = build_document_router(
    DocumentSpec(
        name="supplier-quotations",
        service=SupplierQuotationService,
        label="supplier quotations",
        tag="purchasing",
        party_field="supplier_id",
    )
)


@quotes_router.get("/compare/{rfq_id}", summary="Compare the quotations received for an RFQ")
def compare_quotes(rfq_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("purchasing.supplier_quotation.view")
    service = SupplierQuotationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    return service.compare(rfq_id)


@quotes_router.post("/{document_id}/award", summary="Award a quotation and create the purchase order")
def award_quote(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("purchasing.purchase_order.create")
    service = SupplierQuotationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    order = service.award(document_id)
    db.flush()
    return {**serialise(order), "lines": [serialise(line) for line in order.lines]}


router.include_router(quotes_router, prefix="/supplier-quotations")

orders_router = build_document_router(
    DocumentSpec(
        name="purchase-orders",
        service=PurchaseOrderService,
        label="purchase orders",
        tag="purchasing",
        party_field="supplier_id",
        extra_actions={"receipt": "create_receipt", "invoice": "create_invoice"},
    )
)


@orders_router.get("/{document_id}/pending", summary="Undelivered and unbilled quantities")
def order_pending(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("purchasing.purchase_order.view")
    service = PurchaseOrderService(db, current.company_id, user_id=current.id)
    order = service.get_document(document_id)
    items = []
    for line in order.lines:
        items.append(
            {
                "line_id": str(line.id),
                "product_id": str(line.product_id) if line.product_id else None,
                "ordered": str(line.quantity),
                "received": str(line.received_quantity or 0),
                "invoiced": str(line.invoiced_quantity or 0),
                "pending_receipt": str(Decimal(line.quantity or 0) - Decimal(line.received_quantity or 0)),
                "pending_invoice": str(Decimal(line.quantity or 0) - Decimal(line.invoiced_quantity or 0)),
            }
        )
    return {"order_id": str(order.id), "document_no": order.document_no, "items": items}


@orders_router.get("/{document_id}/print", summary="Printable purchase order")
def order_print(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("purchasing.purchase_order.print")
    from app.api.documents import print_payload

    service = PurchaseOrderService(db, current.company_id, user_id=current.id)
    return print_payload(db, current, service.get_document(document_id), "lines")


router.include_router(orders_router, prefix="/purchase-orders")

router.include_router(
    build_document_router(
        DocumentSpec(
            name="goods-receipts",
            service=GoodsReceiptService,
            label="goods receipts",
            tag="purchasing",
            party_field="supplier_id",
        )
    ),
    prefix="/goods-receipts",
)

purchase_invoices = build_document_router(
    DocumentSpec(
        name="purchase-invoices",
        service=PurchaseInvoiceService,
        label="purchase invoices",
        tag="purchasing",
        party_field="supplier_id",
    )
)


@purchase_invoices.get("/{document_id}/payments", summary="Payments allocated to a supplier invoice")
def supplier_invoice_payments(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("purchasing.purchase_invoice.view")
    from app.models.treasury import PaymentAllocation

    rows = db.execute(
        select(PaymentAllocation).where(
            PaymentAllocation.company_id == current.company_id,
            PaymentAllocation.target_document_id == document_id,
            PaymentAllocation.is_reversed.is_(False),
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


router.include_router(purchase_invoices, prefix="/purchase-invoices")

router.include_router(
    build_document_router(
        DocumentSpec(
            name="debit-notes",
            service=DebitNoteService,
            label="debit notes",
            tag="purchasing",
            party_field="supplier_id",
        )
    ),
    prefix="/debit-notes",
)

# --------------------------------------------------------------------------- #
# Supplier catalogue and evaluations
# --------------------------------------------------------------------------- #
@router.get("/supplier-products", summary="Supplier catalogue with last prices")
def list_supplier_products(
    db: DB,
    current: CurrentUserDep,
    supplier_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    preferred_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("suppliers.supplier_product.view")
    stmt = select(SupplierProduct).where(
        SupplierProduct.company_id == current.company_id, SupplierProduct.deleted_at.is_(None)
    )
    if supplier_id:
        stmt = stmt.where(SupplierProduct.supplier_id == supplier_id)
    if product_id:
        stmt = stmt.where(SupplierProduct.product_id == product_id)
    if preferred_only:
        stmt = stmt.where(SupplierProduct.is_preferred.is_(True))
    rows = db.execute(stmt.order_by(SupplierProduct.last_price).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.put("/suppliers/{supplier_id}/products", summary="Upsert a supplier price for an item")
def upsert_supplier_product(
    supplier_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("suppliers.supplier_product.create")
    from app.services.masterdata_service import PartyService

    row = PartyService(db, current.company_id, user_id=current.id).set_supplier_product(supplier_id, payload)
    return serialise(row)


@router.get("/suppliers/{supplier_id}/price-history", summary="Price history recorded from orders and invoices")
def supplier_price_history(
    supplier_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    product_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("suppliers.supplier_price.view")
    stmt = select(SupplierPriceHistory).where(
        SupplierPriceHistory.company_id == current.company_id,
        SupplierPriceHistory.supplier_id == supplier_id,
    )
    if product_id:
        stmt = stmt.where(SupplierPriceHistory.product_id == product_id)
    rows = db.execute(
        stmt.order_by(SupplierPriceHistory.price_date.desc()).limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="supplier-evaluations",
            model=SupplierEvaluation,
            module="suppliers",
            entity="supplier_evaluation",
            filters={"supplier_id": "supplier_id"},
            default_sort="evaluation_date",
            soft_delete=False,
        ),
        tags=["suppliers"],
    ),
    prefix="/supplier-evaluations",
)


@router.post("/supplier-evaluations", status_code=201, summary="Score a supplier")
def evaluate_supplier(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("suppliers.supplier_evaluation.create")
    service = SupplierEvaluationService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    evaluation = service.evaluate(payload)
    db.flush()
    return serialise(evaluation)


@router.get("/supplier-evaluation/scorecard", summary="Average score per supplier")
def supplier_scorecard(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("suppliers.supplier_evaluation.view")
    rows = db.execute(
        select(
            SupplierEvaluation.supplier_id,
            func.count(SupplierEvaluation.id),
            func.coalesce(func.avg(SupplierEvaluation.overall_score), 0),
        )
        .where(SupplierEvaluation.company_id == current.company_id)
        .group_by(SupplierEvaluation.supplier_id)
    ).all()
    return {
        "items": [
            {
                "supplier_id": str(row[0]),
                "evaluations": int(row[1]),
                "average_score": str(Decimal(row[2]).quantize(Decimal("0.01"))),
            }
            for row in rows
        ]
    }


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@router.get("/registers/purchases", summary="Purchase register")
def purchase_register(
    db: DB,
    current: CurrentUserDep,
    date_from: str | None = None,
    date_to: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("purchasing.purchase_invoice.view")
    from datetime import date as date_type

    from app.services.report_service import ReportService

    result = ReportService(db, current.company_id).purchase_register(
        date_from=_parse_date(date_from) or date_type.today().replace(day=1),
        date_to=_parse_date(date_to) or date_type.today(),
        supplier_id=supplier_id,
    )
    return result.to_dict()


@router.get("/registers/open-orders", summary="Purchase orders pending receipt or billing")
def open_purchase_orders(db: DB, current: CurrentUserDep, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    current.require("purchasing.purchase_order.view")
    rows = db.execute(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.company_id == current.company_id,
            PurchaseOrder.status.in_(["approved", "partially_fulfilled", "posted", "fulfilled"]),
        )
        .order_by(PurchaseOrder.document_date.desc())
        .limit(limit)
    ).scalars().all()
    items = []
    for order in rows:
        pending_receipt = sum(
            (Decimal(line.quantity or 0) - Decimal(line.received_quantity or 0) for line in order.lines),
            Decimal("0"),
        )
        pending_invoice = sum(
            (Decimal(line.quantity or 0) - Decimal(line.invoiced_quantity or 0) for line in order.lines),
            Decimal("0"),
        )
        items.append(
            {
                **serialise(order),
                "pending_receipt_quantity": str(pending_receipt),
                "pending_invoice_quantity": str(pending_invoice),
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/reorder-suggestions", summary="What to buy next, from reorder rules and open demand")
def reorder_suggestions(
    db: DB, current: CurrentUserDep, warehouse_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    current.require("inventory.reorder_rule.view")
    from app.services.inventory_service import InventoryService

    items = InventoryService(db, current.company_id).low_stock_items(warehouse_id, limit=limit)
    return {"items": items, "total": len(items)}


def _parse_date(value: str | None):
    from datetime import date

    return date.fromisoformat(value) if value else None


def _unused(*args: Any) -> None:  # pragma: no cover - keeps imports explicit
    return None


_ = (GoodsReceipt, PurchaseRequest, Rfq, SupplierQuotation, guarded_create)

__all__ = ["router"]
