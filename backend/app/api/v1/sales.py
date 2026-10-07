"""Sales: quotations, orders, deliveries, invoices, returns, commission and POS."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError
from app.models.masterdata import PriceList
from app.models.sales import (
    PosCashMovement,
    PosShift,
    PosTerminal,
    SalesCommission,
    SalesOrder,
)
from app.services.audit_service import AuditService
from app.services.sales_service import (
    CreditNoteService,
    DeliveryNoteService,
    PosSaleService,
    PosShiftService,
    PosTerminalService,
    QuotationService,
    SalesInvoiceService,
    SalesOrderService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Lifecycle resources
# --------------------------------------------------------------------------- #
router.include_router(
    build_document_router(
        DocumentSpec(
            name="quotations",
            service=QuotationService,
            label="quotations",
            tag="sales",
            party_field="customer_id",
            extra_actions={"convert-to-order": "convert_to_order"},
        )
    ),
    prefix="/quotations",
)

orders_router = build_document_router(
    DocumentSpec(
        name="sales-orders",
        service=SalesOrderService,
        label="sales orders",
        tag="sales",
        party_field="customer_id",
        extra_actions={"delivery": "create_delivery", "invoice": "create_invoice"},
    )
)


@orders_router.post("/{document_id}/confirm", summary="Confirm a sales order (credit check)")
def confirm_order(
    document_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    current.require("sales.sales_order.approve")
    service = SalesOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.confirm(document_id, allow_credit_override=bool(payload.get("allow_credit_override")))
    db.flush()
    return {**serialise(order), "lines": [serialise(line) for line in order.lines]}


router.include_router(orders_router, prefix="/sales-orders")

router.include_router(
    build_document_router(
        DocumentSpec(
            name="deliveries",
            service=DeliveryNoteService,
            label="delivery notes",
            tag="sales",
            party_field="customer_id",
        )
    ),
    prefix="/deliveries",
)

invoices_router = build_document_router(
    DocumentSpec(
        name="sales-invoices",
        service=SalesInvoiceService,
        label="sales invoices",
        tag="sales",
        party_field="customer_id",
        search_fields=("document_no", "reference"),
    )
)


@invoices_router.get("/{document_id}/payments", summary="Payments allocated to an invoice")
def invoice_payments(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.sales_invoice.view")
    from app.models.treasury import PaymentAllocation

    rows = db.execute(
        select(PaymentAllocation).where(
            PaymentAllocation.company_id == current.company_id,
            PaymentAllocation.target_document_id == document_id,
            PaymentAllocation.is_reversed.is_(False),
        )
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@invoices_router.get("/{document_id}/print", summary="Printable sales invoice")
def invoice_print(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.sales_invoice.print")
    from app.api.documents import print_payload

    service = SalesInvoiceService(db, current.company_id, user_id=current.id)
    return print_payload(db, current, service.get_document(document_id), "lines")


router.include_router(invoices_router, prefix="/sales-invoices")

router.include_router(
    build_document_router(
        DocumentSpec(
            name="credit-notes",
            service=CreditNoteService,
            label="credit notes",
            tag="sales",
            party_field="customer_id",
        )
    ),
    prefix="/credit-notes",
)

# --------------------------------------------------------------------------- #
# Commission and registers
# --------------------------------------------------------------------------- #
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="commissions",
            model=SalesCommission,
            module="sales",
            entity="sales_commission",
            default_sort="created_at",
            filters={"salesperson_id": "salesperson_id", "status": "status", "invoice_id": "invoice_id"},
            create_handler=guarded_create(SalesCommission),
        ),
        tags=["sales"],
    ),
    prefix="/commissions",
)


@router.get("/commissions/summary", summary="Commission per salesperson for a period")
def commission_summary(
    db: DB,
    current: CurrentUserDep,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    current.require("sales.sales_commission.view")
    stmt = (
        select(
            SalesCommission.salesperson_id,
            func.count(SalesCommission.id),
            func.coalesce(func.sum(SalesCommission.commission_amount), 0),
            func.coalesce(func.sum(SalesCommission.base_amount), 0),
        )
        .where(SalesCommission.company_id == current.company_id)
        .group_by(SalesCommission.salesperson_id)
    )
    if date_from:
        stmt = stmt.where(SalesCommission.created_at >= date_from)
    if date_to:
        stmt = stmt.where(SalesCommission.created_at <= date_to)
    rows = db.execute(stmt).all()
    return {
        "items": [
            {
                "salesperson_id": str(row[0]) if row[0] else None,
                "invoices": int(row[1]),
                "commission": str(row[2]),
                "base_amount": str(row[3]),
            }
            for row in rows
        ]
    }


@router.get("/registers/invoices", summary="Sales invoice register")
def invoice_register(
    db: DB,
    current: CurrentUserDep,
    date_from: str | None = None,
    date_to: str | None = None,
    customer_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    current.require("sales.sales_invoice.view")
    from datetime import date as date_type

    from app.services.report_service import ReportService

    result = ReportService(db, current.company_id).sales_register(
        date_from=_parse_date(date_from) or date_type.today().replace(day=1),
        date_to=_parse_date(date_to) or date_type.today(),
        customer_id=customer_id,
        salesperson_id=None,
    )
    return result.to_dict()


@router.get("/registers/open-orders", summary="Orders with undelivered or unbilled quantities")
def open_orders(db: DB, current: CurrentUserDep, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    current.require("sales.sales_order.view")
    rows = db.execute(
        select(SalesOrder)
        .where(
            SalesOrder.company_id == current.company_id,
            SalesOrder.status.in_(["approved", "partially_fulfilled", "posted", "fulfilled"]),
        )
        .order_by(SalesOrder.document_date.desc())
        .limit(limit)
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for order in rows:
        pending_delivery = sum(
            (Decimal(line.quantity or 0) - Decimal(line.delivered_quantity or 0) for line in order.lines), Decimal("0")
        )
        pending_invoice = sum(
            (Decimal(line.quantity or 0) - Decimal(line.invoiced_quantity or 0) for line in order.lines), Decimal("0")
        )
        items.append(
            {
                **serialise(order),
                "pending_delivery_quantity": str(pending_delivery),
                "pending_invoice_quantity": str(pending_invoice),
            }
        )
    return {"items": items, "total": len(items)}


# --------------------------------------------------------------------------- #
# Point of sale
# --------------------------------------------------------------------------- #
@router.get("/pos/terminals", summary="POS terminals")
def list_terminals(db: DB, current: CurrentUserDep, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    current.require("sales.pos_terminal.view")
    stmt = select(PosTerminal).where(PosTerminal.company_id == current.company_id)
    if branch_id:
        stmt = stmt.where(PosTerminal.branch_id == branch_id)
    rows = db.execute(stmt.order_by(PosTerminal.code)).scalars().all()
    shifts = PosShiftService(db, current.company_id, user_id=current.id)
    items = []
    for row in rows:
        payload = serialise(row)
        shift = shifts.current_shift(terminal_id=row.id)
        payload["open_shift_id"] = str(shift.id) if shift else None
        items.append(payload)
    return {"items": items}


@router.post("/pos/terminals", status_code=201, summary="Create a POS terminal")
def create_terminal(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.pos_terminal.create")
    terminal = PosTerminalService(db, current.company_id, user_id=current.id).quick_setup(payload)
    db.flush()
    AuditService(db, audit_context(current)).log_create(
        terminal, entity_type="pos_terminal", label=terminal.code
    )
    return serialise(terminal)


@router.get("/pos/shifts", summary="POS shifts")
def list_shifts(
    db: DB,
    current: CurrentUserDep,
    terminal_id: uuid.UUID | None = None,
    open_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    current.require("sales.pos_shift.view")
    stmt = select(PosShift).where(PosShift.company_id == current.company_id)
    if terminal_id:
        stmt = stmt.where(PosShift.terminal_id == terminal_id)
    if open_only:
        stmt = stmt.where(PosShift.status != "closed")
    rows = db.execute(stmt.order_by(PosShift.opened_at.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@router.post("/pos/shifts/open", status_code=201, summary="Open a cashier shift")
def open_shift(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.pos_shift.create")
    service = PosShiftService(db, current.company_id, user_id=current.id)
    shift = service.open_shift(
        terminal_id=uuid.UUID(str(payload.get("terminal_id"))),
        cashier_id=uuid.UUID(str(payload["cashier_id"])) if payload.get("cashier_id") else current.id,
        opening_cash=Decimal(str(payload.get("opening_cash", 0))),
    )
    db.flush()
    return serialise(shift)


@router.post("/pos/shifts/{shift_id}/close", summary="Close a shift with cash reconciliation")
def close_shift(
    shift_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("sales.pos_shift.edit")
    shift = PosShiftService(db, current.company_id, user_id=current.id).close_shift(
        shift_id,
        counted_cash=Decimal(str(payload.get("counted_cash", 0))),
        notes=payload.get("notes"),
    )
    db.flush()
    return serialise(shift)


@router.get("/pos/shifts/{shift_id}/z-report", summary="Z report of a shift")
def z_report(shift_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.pos_shift.view")
    service = PosShiftService(db, current.company_id, user_id=current.id)
    shift = service.get_document(shift_id) if hasattr(service, "get_document") else db.get(PosShift, shift_id)
    if shift is None:
        raise NotFoundError("Shift not found", id=str(shift_id))
    return service.z_report(shift)


@router.post("/pos/shifts/{shift_id}/cash-movement", summary="Cash in/out during a shift")
def cash_movement(
    shift_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("sales.pos_shift.edit")
    service = PosShiftService(db, current.company_id, user_id=current.id)
    shift = db.get(PosShift, shift_id)
    if shift is None or shift.company_id != current.company_id:
        raise NotFoundError("Shift not found", id=str(shift_id))
    movement = service.cash_movement(
        shift,
        movement_type=payload.get("movement_type", "in"),
        amount=Decimal(str(payload.get("amount", 0))),
        reason=payload.get("reason"),
    )
    db.flush()
    return serialise(movement)


@router.post("/pos/sales", status_code=201, summary="Ring up a POS sale")
def pos_sale(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.pos_sale.create")
    service = PosSaleService(db, current.company_id, user_id=current.id)
    invoice = service.create_sale(payload)
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


@router.post("/pos/sales/{invoice_id}/post", summary="Post a POS sale and take payment")
def pos_sale_post(invoice_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("sales.pos_sale.create")
    service = PosSaleService(db, current.company_id, user_id=current.id)
    invoice = service.get_document(invoice_id)
    service.post(invoice, allow_draft=True)
    db.flush()
    return {**serialise(invoice), "lines": [serialise(line) for line in invoice.lines]}


@router.post("/pos/sales/{invoice_id}/return", summary="POS return against a posted sale")
def pos_return(
    invoice_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("sales.pos_sale.create")
    from app.services.sales_service import CreditNoteService

    service = CreditNoteService(db, current.company_id, user_id=current.id)
    payload = dict(payload)
    payload.setdefault("invoice_id", str(invoice_id))
    payload.setdefault("reason", "POS return")
    note = service.create(payload)
    note.status = "approved"
    db.flush()
    service.post(note, allow_draft=True)
    db.flush()
    return {**serialise(note), "lines": [serialise(line) for line in note.lines]}


@router.get("/pos/cash-movements", summary="Cash movements of a shift")
def list_cash_movements(
    db: DB, current: CurrentUserDep, shift_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    current.require("sales.pos_shift.view")
    stmt = select(PosCashMovement).where(PosCashMovement.company_id == current.company_id)
    if shift_id:
        stmt = stmt.where(PosCashMovement.shift_id == shift_id)
    rows = db.execute(stmt.order_by(PosCashMovement.created_at.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows]}


@router.get("/pos/lookup", summary="Barcode search used by the POS screen")
def pos_lookup(db: DB, current: CurrentUserDep, code: str = Query(...)) -> dict[str, Any]:
    current.require("sales.pos_sale.view")
    from app.models.inventory import StockBalance
    from app.models.masterdata import Product

    term = code.strip()
    product = db.execute(
        select(Product).where(
            Product.company_id == current.company_id,
            Product.deleted_at.is_(None),
            (Product.barcode == term) | (Product.sku == term),
        )
    ).scalars().first()
    if product is None:
        product = db.execute(
            select(Product)
            .where(Product.company_id == current.company_id, Product.name.ilike(f"%{term}%"))
            .limit(1)
        ).scalars().first()
    if product is None:
        raise NotFoundError(f"No item matches '{code}'")
    on_hand = db.execute(
        select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
            StockBalance.company_id == current.company_id, StockBalance.product_id == product.id
        )
    ).scalar_one()
    return {
        **serialise(product, ["id", "sku", "barcode", "name", "name_ar", "sales_price", "unit_id", "sales_tax_id", "product_type"]),
        "price": str(product.sales_price or 0),
        "on_hand": str(on_hand),
    }


# --------------------------------------------------------------------------- #
# Price lists (sales view)
# --------------------------------------------------------------------------- #
@router.get("/price-lists", summary="Price lists available for sales")
def list_price_lists(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("inventory.price_list.view")
    rows = db.execute(
        select(PriceList).where(
            PriceList.company_id == current.company_id, PriceList.deleted_at.is_(None)
        ).order_by(PriceList.code)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows]}


def _parse_date(value: str | None):
    from datetime import date

    return date.fromisoformat(value) if value else None


__all__ = ["router"]
