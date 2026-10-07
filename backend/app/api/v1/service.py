"""Service and maintenance: requests, tickets, work orders, contracts, warranty."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.api.documents import DocumentSpec, build_document_router
from app.core.errors import NotFoundError, ValidationFailure
from app.models.service import (
    ServiceContract,
    ServiceContractAsset,
    Ticket,
    TicketMessage,
    Warranty,
    WorkOrder,
)
from app.services.service_service import (
    ServiceContractService,
    ServiceRequestService,
    TechnicianScheduleService,
    TicketService,
    WarrantyService,
    WorkOrderService,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Service requests
# --------------------------------------------------------------------------- #
@router.get("/requests", summary="Service requests")
def list_requests(
    db: DB,
    current: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
    customer_id: uuid.UUID | None = None,
    open_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("service.service_request.view")
    rows = ServiceRequestService(db, current.company_id, user_id=current.id).list(
        status=status_filter, customer_id=customer_id, open_only=open_only, limit=limit
    )
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/requests", status_code=201, summary="Log a service request")
def create_request(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.service_request.create")
    request = ServiceRequestService(db, current.company_id, user_id=current.id).create(payload)
    db.flush()
    return serialise(request)


@router.get("/requests/{request_id}", summary="Service request detail")
def get_request(request_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.service_request.view")
    request = ServiceRequestService(db, current.company_id, user_id=current.id).get(request_id)
    return serialise(request)


@router.post("/requests/{request_id}/assign", summary="Assign a request")
def assign_request(request_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.service_request.edit")
    request = ServiceRequestService(db, current.company_id, user_id=current.id).assign(
        request_id, payload.get("user_id") or current.id
    )
    return serialise(request)


@router.post("/requests/{request_id}/ticket", status_code=201, summary="Open a ticket for a request")
def request_to_ticket(
    request_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.ticket.create")
    ticket = ServiceRequestService(db, current.company_id, user_id=current.id).create_ticket(
        request_id, payload or None
    )
    db.flush()
    return serialise(ticket)


@router.post("/requests/{request_id}/work-order", status_code=201, summary="Raise a work order for a request")
def request_to_work_order(
    request_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.work_order.create")
    order = ServiceRequestService(db, current.company_id, user_id=current.id).create_work_order(
        request_id, payload or None
    )
    db.flush()
    return serialise(order)


@router.post("/requests/{request_id}/close", summary="Close a service request")
def close_request(
    request_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.service_request.edit")
    request = ServiceRequestService(db, current.company_id, user_id=current.id).close(
        request_id, resolution=payload.get("resolution")
    )
    return serialise(request)


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
@router.get("/tickets", summary="Tickets with SLA state")
def list_tickets(
    db: DB,
    current: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
    assigned_to_id: uuid.UUID | None = None,
    breached_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("service.ticket.view")
    rows = TicketService(db, current.company_id, user_id=current.id).list(
        status=status_filter, assigned_to_id=assigned_to_id, breached_only=breached_only, limit=limit
    )
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/tickets", status_code=201, summary="Open a ticket")
def create_ticket(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.create")
    ticket = TicketService(db, current.company_id, user_id=current.id).create(payload)
    db.flush()
    return serialise(ticket)


@router.get("/tickets/queue", summary="Ticket queue by team")
def ticket_queue(db: DB, current: CurrentUserDep, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    current.require("service.ticket.view")
    return TicketService(db, current.company_id, user_id=current.id).queue(limit=limit)


@router.get("/tickets/{ticket_id}", summary="Ticket with conversation")
def get_ticket(ticket_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.view")
    service = TicketService(db, current.company_id, user_id=current.id)
    ticket = service.get(ticket_id)
    messages = db.execute(
        select(TicketMessage)
        .where(TicketMessage.company_id == current.company_id, TicketMessage.ticket_id == ticket_id)
        .order_by(TicketMessage.created_at)
    ).scalars().all()
    return {**serialise(ticket), "messages": [serialise(row) for row in messages]}


@router.post("/tickets/{ticket_id}/messages", status_code=201, summary="Reply on a ticket")
def add_ticket_message(
    ticket_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.ticket.edit")
    service = TicketService(db, current.company_id, user_id=current.id)
    payload = dict(payload)
    payload.setdefault("author_id", str(current.id))
    message = service.add_message(ticket_id, payload)
    db.flush()
    return serialise(message)


@router.post("/tickets/{ticket_id}/assign", summary="Assign a ticket")
def assign_ticket(ticket_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.edit")
    ticket = TicketService(db, current.company_id, user_id=current.id).assign(
        ticket_id, payload.get("user_id") or current.id
    )
    return serialise(ticket)


@router.post("/tickets/{ticket_id}/status", summary="Change the ticket status")
def set_ticket_status(ticket_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.edit")
    ticket = TicketService(db, current.company_id, user_id=current.id).set_status(
        ticket_id, payload.get("status")
    )
    return serialise(ticket)


@router.post("/tickets/{ticket_id}/resolve", summary="Resolve a ticket")
def resolve_ticket(ticket_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.edit")
    ticket = TicketService(db, current.company_id, user_id=current.id).resolve(
        ticket_id,
        resolution=payload.get("resolution") or "resolved",
        satisfaction_score=payload.get("satisfaction_score"),
    )
    return serialise(ticket)


@router.post("/tickets/{ticket_id}/close", summary="Close a ticket")
def close_ticket(ticket_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.ticket.edit")
    ticket = TicketService(db, current.company_id, user_id=current.id).close(ticket_id)
    return serialise(ticket)


# --------------------------------------------------------------------------- #
# Work orders
# --------------------------------------------------------------------------- #
work_orders = build_document_router(
    DocumentSpec(
        name="work-orders",
        service=WorkOrderService,
        label="work orders",
        tag="service",
        party_field="customer_id",
        search_fields=("document_no", "reference"),
        extra_actions={"invoice": "invoice"},
    )
)


@work_orders.post("/{document_id}/start", summary="Start work on site")
def start_work_order(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.work_order.edit")
    service = WorkOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.start(document_id)
    db.flush()
    return serialise(order)


@work_orders.post("/{document_id}/schedule", summary="Schedule a visit")
def schedule_work_order(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.work_order.edit")
    service = WorkOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.schedule(
        document_id,
        scheduled_date=_datetime(payload.get("scheduled_date")) or datetime.now(),
        technician_id=payload.get("technician_id"),
    )
    db.flush()
    return serialise(order)


@work_orders.post("/{document_id}/complete", summary="Complete the work with labour and parts")
def complete_work_order(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.work_order.edit")
    service = WorkOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    order = service.complete(document_id, payload or None)
    db.flush()
    return serialise(order)


@work_orders.post("/{document_id}/parts", summary="Issue a part to the work order")
def add_work_order_part(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.work_order.edit")
    service = WorkOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    line = service.add_part(document_id, payload)
    db.flush()
    return serialise(line)


@work_orders.post("/{document_id}/labour", summary="Add labour hours")
def add_work_order_labour(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.work_order.edit")
    service = WorkOrderService(db, current.company_id, user_id=current.id, audit_context=audit_context(current, None))
    line = service.add_labour(document_id, payload)
    db.flush()
    return serialise(line)


@work_orders.get("/{document_id}/summary", summary="Work order cost and billing summary")
def work_order_summary(document_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.work_order.view")
    return TechnicianScheduleService(db, current.company_id, user_id=current.id).work_order_summary(document_id)


router.include_router(work_orders, prefix="/work-orders")

# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #
contracts_router = build_document_router(
    DocumentSpec(
        name="contracts",
        service=ServiceContractService,
        label="service contracts",
        tag="service",
        party_field="customer_id",
        search_fields=("document_no", "reference"),
    )
)


@contracts_router.post("/{document_id}/activate", summary="Activate a contract")
def activate_contract(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.service_contract.approve")
    service = ServiceContractService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    contract = service.activate(document_id, signed_by=payload.get("signed_by"))
    db.flush()
    return serialise(contract)


@contracts_router.post("/{document_id}/assets", summary="Cover an asset under the contract")
def add_contract_asset(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.service_contract.edit")
    service = ServiceContractService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    asset = service.add_asset(document_id, payload)
    db.flush()
    return serialise(asset)


@contracts_router.post("/{document_id}/visits", status_code=201, summary="Schedule preventive visits")
def schedule_visits(
    document_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("service.technician_schedule.create")
    service = ServiceContractService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    visits = service.schedule_visits(
        document_id,
        technician_id=payload.get("technician_id"),
        interval_days=int(payload.get("interval_days") or 90),
    )
    db.flush()
    return {"items": [serialise(row) for row in visits], "total": len(visits)}


@contracts_router.post("/{document_id}/visit-log", summary="Log a completed contract visit")
def log_contract_visit(
    document_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.service_contract.edit")
    service = ServiceContractService(
        db, current.company_id, user_id=current.id, audit_context=audit_context(current, None)
    )
    contract = service.record_visit(document_id, note=payload.get("note"))
    db.flush()
    return serialise(contract)


router.include_router(contracts_router, prefix="/contracts")


@router.post("/contracts/expire-due", summary="Expire contracts whose end date has passed")
def expire_contracts(
    db: DB, current: CurrentUserDep, as_of: date | None = None
) -> dict[str, Any]:
    current.require("service.service_contract.edit")
    service = ServiceContractService(db, current.company_id, user_id=current.id)
    expired = service.expire_due_contracts(as_of=as_of)
    db.flush()
    return {"expired": [serialise(row) for row in expired] if isinstance(expired, list) else expired}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="contract-assets",
            model=ServiceContractAsset,
            module="service",
            entity="service_contract",
            filters={"contract_id": "contract_id", "asset_id": "asset_id", "serial_number": "serial_number"},
            soft_delete=False,
            create_handler=guarded_create(ServiceContractAsset),
        ),
        tags=["service"],
    ),
    prefix="/contract-assets",
)

# --------------------------------------------------------------------------- #
# Warranty
# --------------------------------------------------------------------------- #
@router.get("/warranties", summary="Warranties with remaining coverage")
def list_warranties(
    db: DB,
    current: CurrentUserDep,
    customer_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    serial_number: str | None = None,
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("service.warranty.view")
    service = WarrantyService(db, current.company_id, user_id=current.id)
    if active_only:
        rows = service.find_active(
            customer_id=customer_id, product_id=product_id, serial_number=serial_number
        )
        return {"items": [serialise(row) for row in rows], "total": len(rows)}
    stmt = select(Warranty).where(Warranty.company_id == current.company_id, Warranty.deleted_at.is_(None))
    if customer_id:
        stmt = stmt.where(Warranty.customer_id == customer_id)
    if product_id:
        stmt = stmt.where(Warranty.product_id == product_id)
    if serial_number:
        stmt = stmt.where(Warranty.serial_number == serial_number)
    rows = db.execute(stmt.order_by(Warranty.end_date.desc()).limit(limit)).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/warranties", status_code=201, summary="Register a warranty")
def create_warranty(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.warranty.create")
    warranty = WarrantyService(db, current.company_id, user_id=current.id).create(payload)
    db.flush()
    return serialise(warranty)


@router.post("/warranties/from-invoice/{invoice_id}", status_code=201, summary="Create warranties from an invoice")
def warranty_from_invoice(
    invoice_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    days: int = Query(365, ge=1, le=3650),
) -> dict[str, Any]:
    current.require("service.warranty.create")
    warranties = WarrantyService(db, current.company_id, user_id=current.id).create_from_invoice(
        invoice_id, days=days
    )
    db.flush()
    if isinstance(warranties, list):
        return {"items": [serialise(row) for row in warranties], "total": len(warranties)}
    return serialise(warranties)


@router.post("/warranties/{warranty_id}/claim", summary="File a warranty claim")
def warranty_claim(
    warranty_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("service.warranty.edit")
    warranty = WarrantyService(db, current.company_id, user_id=current.id).claim(
        warranty_id, note=payload.get("note")
    )
    db.flush()
    return serialise(warranty)


@router.post("/warranties/expire-due", summary="Expire warranties that ended")
def expire_warranties(db: DB, current: CurrentUserDep, as_of: date | None = None) -> dict[str, Any]:
    current.require("service.warranty.edit")
    result = WarrantyService(db, current.company_id, user_id=current.id).expire_due(as_of=as_of)
    db.flush()
    return {"expired": len(result) if isinstance(result, list) else result}


# --------------------------------------------------------------------------- #
# Technician scheduling
# --------------------------------------------------------------------------- #
@router.get("/schedules", summary="Technician agenda")
def list_schedules(
    db: DB,
    current: CurrentUserDep,
    on_date: date | None = None,
    employee_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("service.technician_schedule.view")
    rows = TechnicianScheduleService(db, current.company_id, user_id=current.id).agenda(
        on_date=on_date or date.today(), employee_id=employee_id
    )
    return {"items": [serialise(row) for row in rows] if not isinstance(rows, dict) else rows}


@router.post("/schedules", status_code=201, summary="Schedule a technician visit")
def schedule_technician(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.technician_schedule.create")
    schedule = TechnicianScheduleService(db, current.company_id, user_id=current.id).schedule(payload)
    db.flush()
    return serialise(schedule)


@router.get("/schedules/utilisation", summary="Technician utilisation for a period")
def technician_utilisation(
    db: DB, current: CurrentUserDep, date_from: date = Query(...), date_to: date = Query(...)
) -> dict[str, Any]:
    current.require("service.technician_schedule.view")
    result = TechnicianScheduleService(db, current.company_id, user_id=current.id).util_sation(
        date_from=date_from, date_to=date_to
    )
    return result if isinstance(result, dict) else {"items": result}


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@router.get("/reports/summary", summary="Service desk KPIs")
def service_summary(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("service.ticket.view")
    today = date.today()
    start = date_from or today.replace(month=1, day=1)
    end = date_to or today
    tickets = db.execute(
        select(Ticket.status, func.count(Ticket.id))
        .where(Ticket.company_id == current.company_id, Ticket.deleted_at.is_(None))
        .group_by(Ticket.status)
    ).all()
    orders = db.execute(
        select(WorkOrder.status, func.count(WorkOrder.id), func.coalesce(func.sum(WorkOrder.total_amount), 0))
        .where(WorkOrder.company_id == current.company_id, WorkOrder.deleted_at.is_(None))
        .group_by(WorkOrder.status)
    ).all()
    breached = db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.company_id == current.company_id, Ticket.is_sla_breached.is_(True)
        )
    ).scalar_one()
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "tickets_by_status": [{"status": row[0], "count": int(row[1])} for row in tickets],
        "work_orders_by_status": [
            {"status": row[0], "count": int(row[1]), "amount": str(row[2])} for row in orders
        ],
        "sla_breached": int(breached),
    }


@router.get("/reports/contract-value", summary="Recurring contract value")
def contract_value(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("service.service_contract.view")
    rows = db.execute(
        select(
            ServiceContract.status,
            func.count(ServiceContract.id),
            func.coalesce(func.sum(ServiceContract.contract_value), 0),
        )
        .where(ServiceContract.company_id == current.company_id, ServiceContract.deleted_at.is_(None))
        .group_by(ServiceContract.status)
    ).all()
    return {
        "items": [
            {"status": row[0], "contracts": int(row[1]), "value": str(row[2])} for row in rows
        ]
    }


def _datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _unused(*args: Any) -> None:  # pragma: no cover
    return None


_ = (NotFoundError, ValidationFailure, Decimal)

__all__ = ["router"]
