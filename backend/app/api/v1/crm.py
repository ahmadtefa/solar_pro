"""CRM: leads, pipeline, opportunities, activities, customers and contacts."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from app.api.crud import ResourceSpec, build_crud_router, guarded_create, serialise
from app.api.deps import DB, CurrentUserDep, audit_context
from app.core.errors import NotFoundError, ValidationFailure
from app.models.crm import Activity, Lead, LeadSource, Opportunity, PipelineStage, SalesTarget
from app.models.masterdata import Contact, Customer
from app.models.sales import SalesInvoice
from app.schemas.masterdata import CustomerCreate
from app.services.audit_service import AuditService
from app.services.masterdata_service import ContactService, PartyService
from app.services.numbering_service import NumberingService

router = APIRouter()

# --------------------------------------------------------------------------- #
# Leads and pipeline
# --------------------------------------------------------------------------- #
@router.get("/leads", summary="Lead pipeline with conversion metrics")
def list_leads(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    status: str | None = None,
    source_id: uuid.UUID | None = None,
    assigned_to_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("crm.lead.view")
    stmt = select(Lead).where(Lead.company_id == current.company_id, Lead.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Lead.contact_name.ilike(f"%{q}%")
            | Lead.company_name.ilike(f"%{q}%")
            | Lead.email.ilike(f"%{q}%")
            | Lead.phone.ilike(f"%{q}%")
        )
    if status:
        stmt = stmt.where(Lead.status == status)
    if source_id:
        stmt = stmt.where(Lead.source_id == source_id)
    if assigned_to_id:
        stmt = stmt.where(Lead.owner_id == assigned_to_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/leads", status_code=201, summary="Capture a lead")
def create_lead(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.lead.create")
    values = _lead_values(payload)
    values.setdefault("status", "new")
    values.setdefault(
        "lead_no",
        NumberingService(db, current.company_id).next_number("lead", prefix="LEAD-", padding=5),
    )
    lead = Lead(company_id=current.company_id, **values)
    db.add(lead)
    db.flush()
    AuditService(db, audit_context(current)).log_create(lead, entity_type="lead", label=_lead_label(lead))
    return serialise(lead)


@router.get("/leads/{lead_id}", summary="Lead detail with its activities")
def get_lead(lead_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.lead.view")
    lead = _get(db, Lead, lead_id, current, "Lead")
    activities = db.execute(
        select(Activity)
        .where(
            Activity.company_id == current.company_id,
            Activity.entity_type == "lead",
            Activity.entity_id == lead_id,
        )
        .order_by(Activity.created_at.desc())
        .limit(50)
    ).scalars().all()
    return {**serialise(lead), "activities": [serialise(row) for row in activities]}


@router.patch("/leads/{lead_id}", summary="Update a lead")
def update_lead(lead_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.lead.edit")
    lead = _get(db, Lead, lead_id, current, "Lead")
    from app.core.pagination import snapshot

    before = snapshot(lead)
    for key, value in _lead_values(payload).items():
        setattr(lead, key, value)
    db.flush()
    AuditService(db, audit_context(current)).log_update(lead, before, entity_type="lead", label=_lead_label(lead))
    return serialise(lead)


@router.post("/leads/{lead_id}/score", summary="Recalculate the lead score")
def score_lead(lead_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.lead.edit")
    lead = _get(db, Lead, lead_id, current, "Lead")
    score = 0
    if lead.email:
        score += 20
    if lead.phone or lead.mobile:
        score += 20
    if lead.company_name:
        score += 10
    if lead.expected_value and Decimal(lead.expected_value) > 0:
        score += 30
    if lead.status in {"qualified", "converted"}:
        score += 20
    lead.score = min(score, 100)
    db.flush()
    return {"lead_id": str(lead.id), "score": lead.score}


@router.post("/leads/{lead_id}/convert", summary="Convert a lead into a customer and/or opportunity")
def convert_lead(
    lead_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("crm.lead.edit")
    lead = _get(db, Lead, lead_id, current, "Lead")
    party = PartyService(db, current.company_id, user_id=current.id)
    customer_id = None
    if payload.get("customer_id"):
        customer_id = uuid.UUID(str(payload["customer_id"]))
        party.get_customer(customer_id)
    elif payload.get("create_customer", True):
        customer = party.create_customer(
            {
                "name": lead.company_name or lead.contact_name,
                "email": lead.email,
                "phone": lead.phone or lead.mobile,
                "city": lead.city,
                "country_code": lead.country_code,
                "salesperson_id": lead.owner_id,
                "notes": f"Converted from lead {lead.lead_no or lead.id}",
            }
        )
        customer_id = customer.id
    opportunity_id = None
    if payload.get("create_opportunity", True):
        stage = _first_stage(db, current.company_id)
        opportunity = Opportunity(
            company_id=current.company_id,
            opportunity_no=NumberingService(db, current.company_id).next_number(
                "opportunity", prefix="OPP-", padding=5
            ),
            name=payload.get("opportunity_name") or f"{_lead_label(lead)} opportunity",
            customer_id=customer_id,
            lead_id=lead.id,
            stage_id=stage.id if stage else None,
            stage=stage.name if stage else None,
            amount=lead.expected_value or Decimal("0"),
            currency_code=lead.currency_code,
            probability=payload.get("probability", stage.probability if stage else 30),
            expected_close_date=payload.get("expected_close_date") or lead.expected_close_date,
            owner_id=lead.owner_id or current.id,
        )
        db.add(opportunity)
        db.flush()
        opportunity_id = opportunity.id
    lead.status = "converted"
    lead.converted_customer_id = customer_id
    lead.converted_opportunity_id = opportunity_id
    lead.converted_at = datetime.now()
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "update", lead, entity_type="lead", label=lead.name, remarks="converted", new_values={"customer_id": str(customer_id)}
    )
    return {
        "lead_id": str(lead.id),
        "customer_id": str(customer_id) if customer_id else None,
        "opportunity_id": str(opportunity_id) if opportunity_id else None,
    }


@router.get("/leads/pipeline/summary", summary="Pipeline funnel by stage")
def pipeline_summary(db: DB, current: CurrentUserDep, owner_id: uuid.UUID | None = None) -> dict[str, Any]:
    current.require("crm.opportunity.view")
    stmt = (
        select(Opportunity.stage_id, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.amount), 0))
        .where(Opportunity.company_id == current.company_id, Opportunity.deleted_at.is_(None))
        .group_by(Opportunity.stage_id)
    )
    if owner_id:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
    counts = {row[0]: (int(row[1]), row[2]) for row in db.execute(stmt).all()}
    stages = db.execute(
        select(PipelineStage)
        .where(PipelineStage.company_id == current.company_id)
        .order_by(PipelineStage.sequence_no)
    ).scalars().all()
    items = []
    for stage in stages:
        count, amount = counts.get(stage.id, (0, Decimal("0")))
        items.append(
            {
                "stage_id": str(stage.id),
                "stage": stage.name,
                "probability": stage.probability,
                "opportunities": count,
                "amount": str(amount),
                "weighted": str((Decimal(amount) * Decimal(stage.probability or 0) / 100).quantize(Decimal("0.01"))),
            }
        )
    return {"items": items, "total_amount": str(sum(Decimal(item["amount"]) for item in items))}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="lead-sources",
            model=LeadSource,
            module="crm",
            entity="lead_source",
            search_fields=["code", "name"],
            label_field="name",
            create_handler=guarded_create(LeadSource, unique=[("code", "Lead source code")]),
        ),
        tags=["crm"],
    ),
    prefix="/lead-sources",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="pipeline-stages",
            model=PipelineStage,
            module="crm",
            entity="pipeline_stage",
            search_fields=["name"],
            label_field="name",
            default_sort="sequence_no",
            create_handler=guarded_create(PipelineStage),
        ),
        tags=["crm"],
    ),
    prefix="/pipeline-stages",
)
router.include_router(
    build_crud_router(
        ResourceSpec(
            name="opportunities",
            model=Opportunity,
            module="crm",
            entity="opportunity",
            search_fields=["opportunity_no", "name"],
            create_handler=guarded_create(Opportunity),
        ),
        tags=["crm"],
    ),
    prefix="/opportunities",
)


@router.post("/opportunities/{opportunity_id}/stage", summary="Move an opportunity to another stage")
def move_opportunity(
    opportunity_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("crm.opportunity.edit")
    opportunity = _get(db, Opportunity, opportunity_id, current, "Opportunity")
    stage_id = payload.get("stage_id")
    if not stage_id:
        raise ValidationFailure("stage_id is required")
    stage = _get(db, PipelineStage, uuid.UUID(str(stage_id)), current, "Pipeline stage")
    opportunity.stage_id = stage.id
    opportunity.stage = stage.name
    if stage.probability is not None:
        opportunity.probability = stage.probability
    opportunity.weighted_amount = (
        Decimal(opportunity.amount or 0) * Decimal(stage.probability or 0) / 100
    ).quantize(Decimal("0.01"))
    if stage.is_won:
        opportunity.is_won = True
        opportunity.is_lost = False
        opportunity.actual_close_date = date.today()
    elif stage.is_lost:
        opportunity.is_lost = True
        opportunity.is_won = False
        opportunity.actual_close_date = date.today()
        opportunity.lost_reason = payload.get("lost_reason") or opportunity.lost_reason
    db.flush()
    return serialise(opportunity)


@router.get("/opportunities/forecast", summary="Weighted sales forecast")
def forecast(
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
    owner_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("crm.opportunity.view")
    stmt = select(Opportunity).where(
        Opportunity.company_id == current.company_id,
        Opportunity.deleted_at.is_(None),
        Opportunity.is_won.is_(False),
        Opportunity.is_lost.is_(False),
    )
    if date_from:
        stmt = stmt.where(Opportunity.expected_close_date >= date_from)
    if date_to:
        stmt = stmt.where(Opportunity.expected_close_date <= date_to)
    if owner_id:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
    rows = db.execute(stmt).scalars().all()
    total = sum((Decimal(row.amount or 0) for row in rows), Decimal("0"))
    weighted = sum((Decimal(row.amount or 0) * Decimal(row.probability or 0) / 100 for row in rows), Decimal("0"))
    return {
        "opportunities": len(rows),
        "pipeline_value": str(total.quantize(Decimal("0.01"))),
        "weighted_forecast": str(weighted.quantize(Decimal("0.01"))),
        "by_month": _forecast_by_month(rows),
    }


# --------------------------------------------------------------------------- #
# Activities and follow-ups
# --------------------------------------------------------------------------- #
@router.get("/activities", summary="Activities and follow-ups")
def list_activities(
    db: DB,
    current: CurrentUserDep,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    pending_only: bool = False,
    include_done: bool = True,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    current.require("crm.activity.view")
    stmt = select(Activity).where(Activity.company_id == current.company_id, Activity.deleted_at.is_(None))
    if entity_type:
        stmt = stmt.where(Activity.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Activity.entity_id == entity_id)
    if owner_id:
        stmt = stmt.where(Activity.owner_id == owner_id)
    if pending_only or not include_done:
        stmt = stmt.where(Activity.status.notin_(["done", "cancelled"]))
    rows = db.execute(
        stmt.order_by(Activity.due_date.asc().nulls_last(), Activity.created_at.desc()).limit(limit)
    ).scalars().all()
    today = date.today()
    items = []
    for row in rows:
        payload = serialise(row)
        payload["overdue"] = bool(
            row.due_date and row.status not in {"done", "cancelled"} and row.due_date < today
        )
        items.append(payload)
    return {
        "items": items,
        "total": len(items),
        "pending": sum(1 for item in items if item["status"] not in {"done", "cancelled"}),
    }


@router.post("/activities", status_code=201, summary="Log an activity or schedule a follow-up")
def create_activity(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.activity.create")
    values = _activity_values(payload, current.id)
    activity = Activity(company_id=current.company_id, **values)
    db.add(activity)
    db.flush()
    AuditService(db, audit_context(current)).log_create(
        activity, entity_type="activity", label=activity.subject
    )
    return serialise(activity)


@router.post("/activities/{activity_id}/complete", summary="Complete an activity")
def complete_activity(
    activity_id: uuid.UUID, db: DB, current: CurrentUserDep, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    current.require("crm.activity.edit")
    activity = _get(db, Activity, activity_id, current, "Activity")
    activity.status = payload.get("status") or "done"
    activity.completed_at = datetime.now()
    if payload.get("outcome"):
        activity.outcome = payload["outcome"]
    if payload.get("description"):
        activity.description = payload["description"]
    db.flush()
    return serialise(activity)


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="sales-targets",
            model=SalesTarget,
            module="crm",
            entity="sales_target",
            filters={"salesperson_id": "salesperson_id", "branch_id": "branch_id", "period_type": "period_type"},
            create_handler=guarded_create(SalesTarget),
        ),
        tags=["crm"],
    ),
    prefix="/sales-targets",
)


# --------------------------------------------------------------------------- #
# Customers and contacts
# --------------------------------------------------------------------------- #
@router.get("/customers", summary="Customers with balances and credit headroom")
def list_customers(
    db: DB,
    current: CurrentUserDep,
    q: str | None = None,
    group_id: uuid.UUID | None = None,
    salesperson_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    current.require("crm.customer.view")
    stmt = select(Customer).where(Customer.company_id == current.company_id, Customer.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Customer.name.ilike(f"%{q}%")
            | Customer.name_ar.ilike(f"%{q}%")
            | Customer.code.ilike(f"%{q}%")
            | Customer.email.ilike(f"%{q}%")
            | Customer.phone.ilike(f"%{q}%")
        )
    if group_id:
        stmt = stmt.where(Customer.customer_group_id == group_id)
    if salesperson_id:
        stmt = stmt.where(Customer.salesperson_id == salesperson_id)
    if not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Customer.name).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    balances = _customer_balances(db, current, [row.id for row in rows])
    items = []
    for row in rows:
        payload = serialise(row)
        payload["outstanding"] = str(balances.get(row.id, Decimal("0")))
        payload["available_credit"] = str(Decimal(row.credit_limit or 0) - balances.get(row.id, Decimal("0")))
        items.append(payload)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("/customers", status_code=201, summary="Create a customer")
def create_customer(payload: CustomerCreate, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.customer.create")
    customer = PartyService(db, current.company_id, user_id=current.id).create_customer(payload.data())
    return serialise(customer)


@router.get("/customers/{customer_id}", summary="Customer 360: profile, credit, invoices and contacts")
def get_customer(customer_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.customer.view")
    party = PartyService(db, current.company_id, user_id=current.id)
    customer = party.get_customer(customer_id)
    payload = serialise(customer)
    payload["credit"] = party.credit_position(customer_id)
    payload["contacts"] = [serialise(row) for row in ContactService(db, current.company_id).list_for(party_type="customer", party_id=customer_id)]
    payload["invoices"] = [
        serialise(row)
        for row in db.execute(
            select(SalesInvoice)
            .where(SalesInvoice.company_id == current.company_id, SalesInvoice.customer_id == customer_id)
            .order_by(SalesInvoice.document_date.desc())
            .limit(20)
        ).scalars().all()
    ]
    payload["timeline"] = _customer_timeline(db, current, customer_id)
    return payload


@router.patch("/customers/{customer_id}", summary="Update a customer")
def update_customer(customer_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.customer.edit")
    customer = PartyService(db, current.company_id, user_id=current.id).update_customer(customer_id, payload)
    return serialise(customer)


@router.post("/customers/{customer_id}/credit-hold", summary="Place or release a credit hold")
def credit_hold(
    customer_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("crm.customer.edit")
    customer = PartyService(db, current.company_id).get_customer(customer_id)
    customer.is_credit_hold = bool(payload.get("on_hold", True))
    customer.credit_hold_reason = payload.get("reason")
    db.flush()
    AuditService(db, audit_context(current)).log_action(
        "update",
        customer,
        entity_type="customer",
        label=customer.code,
        remarks="credit hold",
        new_values={"is_credit_hold": customer.is_credit_hold, "reason": customer.credit_hold_reason},
    )
    return {"customer_id": str(customer.id), "is_credit_hold": customer.is_credit_hold}


@router.get("/customers/{customer_id}/credit", summary="Credit position of a customer")
def customer_credit(customer_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.customer.view")
    return PartyService(db, current.company_id).credit_position(customer_id)


@router.get("/customers/{customer_id}/statement", summary="Customer statement of account")
def customer_statement(
    customer_id: uuid.UUID,
    db: DB,
    current: CurrentUserDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    current.require("crm.customer.view")
    from app.services.report_service import ReportService

    party = PartyService(db, current.company_id).get_customer(customer_id)
    today = date.today()
    statement = ReportService(db, current.company_id).customer_statement(
        customer_id=customer_id,
        date_from=date_from or today.replace(month=1, day=1),
        date_to=date_to or today,
    )
    return {"customer": {"id": str(party.id), "code": party.code, "name": party.name}, **statement.to_dict()}


@router.get("/customers/{customer_id}/contacts", summary="Contacts of a customer")
def customer_contacts(customer_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.contact.view")
    PartyService(db, current.company_id).get_customer(customer_id)
    rows = ContactService(db, current.company_id).list_for(party_type="customer", party_id=customer_id)
    return {"items": [serialise(row) for row in rows]}


@router.post("/customers/{customer_id}/contacts", status_code=201, summary="Add a contact to a customer")
def add_customer_contact(
    customer_id: uuid.UUID, payload: dict[str, Any], db: DB, current: CurrentUserDep
) -> dict[str, Any]:
    current.require("crm.contact.create")
    contact = PartyService(db, current.company_id, user_id=current.id).add_contact(
        party_type="customer", party_id=customer_id, payload=payload
    )
    return serialise(contact)


@router.get("/customers/timeline/{customer_id}", summary="Customer interaction timeline")
def customer_timeline(customer_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("crm.customer.view")
    return {"items": _customer_timeline(db, current, customer_id)}


router.include_router(
    build_crud_router(
        ResourceSpec(
            name="contacts",
            model=Contact,
            module="crm",
            entity="contact",
            search_fields=["first_name", "last_name", "email", "phone"],
            default_sort="first_name",
            filters={"party_type": "party_type", "customer_id": "customer_id", "supplier_id": "supplier_id"},
            create_handler=guarded_create(Contact),
        ),
        tags=["crm"],
    ),
    prefix="/contacts",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_LEAD_FIELDS = {
    "lead_no",
    "company_name",
    "contact_name",
    "email",
    "phone",
    "mobile",
    "whatsapp",
    "website",
    "job_title",
    "source_id",
    "stage_id",
    "status",
    "priority",
    "expected_value",
    "expected_close_date",
    "currency_code",
    "industry",
    "city",
    "country_code",
    "address",
    "owner_id",
    "notes",
    "interest",
    "tags",
    "next_follow_up_at",
    "lost_reason",
}


def _lead_values(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in _LEAD_FIELDS or value is None:
            continue
        if key.endswith("_id"):
            values[key] = uuid.UUID(str(value))
        elif key in {"expected_value"}:
            values[key] = Decimal(str(value))
        else:
            values[key] = value
    if not values.get("contact_name") and not values.get("company_name"):
        raise ValidationFailure("A lead needs a contact name or a company name")
    return values


_ACTIVITY_FIELDS = {
    "activity_type",
    "subject",
    "description",
    "entity_type",
    "entity_id",
    "lead_id",
    "opportunity_id",
    "customer_id",
    "supplier_id",
    "project_id",
    "ticket_id",
    "due_date",
    "start_time",
    "end_time",
    "priority",
    "status",
    "outcome",
    "location",
    "assigned_to_id",
    "completed_at",
    "duration_minutes",
    "remind_at",
    "is_recurring",
    "recurrence_rule",
}


def _activity_values(payload: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    values: dict[str, Any] = {"owner_id": user_id}
    for key, value in payload.items():
        if key not in _ACTIVITY_FIELDS or value is None:
            continue
        if key.endswith("_id"):
            values[key] = uuid.UUID(str(value))
        elif key == "due_date":
            values[key] = date.fromisoformat(str(value)) if not isinstance(value, date) else value
        elif key in {"start_time", "end_time", "remind_at"}:
            values[key] = datetime.fromisoformat(str(value))
        else:
            values[key] = value
    if not values.get("subject"):
        raise ValidationFailure("The activity subject is required")
    values.setdefault("activity_type", "call")
    values.setdefault("status", "open")
    return values


def _lead_label(lead: Lead) -> str:
    return lead.lead_no or lead.company_name or lead.contact_name or str(lead.id)


def _get(db: DB, model: type[Any], identifier: uuid.UUID, current: CurrentUserDep, label: str) -> Any:
    row = db.get(model, identifier)
    if row is None or row.company_id != current.company_id:
        raise NotFoundError(f"{label} not found", id=str(identifier))
    return row


def _first_stage(db: DB, company_id: uuid.UUID) -> PipelineStage | None:
    return db.execute(
        select(PipelineStage)
        .where(PipelineStage.company_id == company_id)
        .order_by(PipelineStage.sequence_no)
    ).scalars().first()


def _customer_balances(db: DB, current: CurrentUserDep, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not customer_ids:
        return {}
    rows = db.execute(
        select(SalesInvoice.customer_id, func.coalesce(func.sum(SalesInvoice.balance_amount), 0))
        .where(
            SalesInvoice.company_id == current.company_id,
            SalesInvoice.customer_id.in_(customer_ids),
            SalesInvoice.status.in_(["posted", "partially_fulfilled"]),
        )
        .group_by(SalesInvoice.customer_id)
    ).all()
    return {row[0]: Decimal(row[1]) for row in rows}


def _customer_timeline(db: DB, current: CurrentUserDep, customer_id: uuid.UUID) -> list[dict[str, Any]]:
    from app.models.identity import AuditLog

    events: list[dict[str, Any]] = []
    activities = db.execute(
        select(Activity)
        .where(
            Activity.company_id == current.company_id,
            Activity.entity_type == "customer",
            Activity.entity_id == customer_id,
        )
        .order_by(Activity.created_at.desc())
        .limit(50)
    ).scalars().all()
    for activity in activities:
        events.append(
            {
                "at": activity.due_date.isoformat() if activity.due_date else activity.created_at.isoformat(),
                "kind": activity.activity_type,
                "title": activity.subject,
                "detail": activity.outcome or activity.description,
                "metadata": {"status": activity.status, "id": str(activity.id)},
            }
        )
    invoices = db.execute(
        select(SalesInvoice)
        .where(SalesInvoice.company_id == current.company_id, SalesInvoice.customer_id == customer_id)
        .order_by(SalesInvoice.document_date.desc())
        .limit(50)
    ).scalars().all()
    for invoice in invoices:
        events.append(
            {
                "at": invoice.document_date.isoformat(),
                "kind": "invoice",
                "title": f"{invoice.document_no} · {invoice.total_amount}",
                "detail": invoice.status,
                "metadata": {"id": str(invoice.id), "status": invoice.status},
            }
        )
    audits = db.execute(
        select(AuditLog)
        .where(AuditLog.company_id == current.company_id, AuditLog.entity_id == customer_id)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    ).scalars().all()
    for row in audits:
        events.append(
            {
                "at": row.created_at.isoformat() if row.created_at else None,
                "kind": f"audit:{row.action}",
                "title": row.entity_label or row.entity_type,
                "detail": row.remarks,
                "actor": row.user_email,
                "metadata": {"id": str(row.id)},
            }
        )
    events.sort(key=lambda item: item["at"] or "", reverse=True)
    return events


def _forecast_by_month(rows: list[Opportunity]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Decimal]] = {}
    follow_up = date.today() + timedelta(days=1)
    for row in rows:
        expected = row.expected_close_date or follow_up
        key = expected.strftime("%Y-%m")
        bucket = buckets.setdefault(key, {"amount": Decimal("0"), "weighted": Decimal("0"), "count": Decimal("0")})
        bucket["amount"] += Decimal(row.amount or 0)
        bucket["weighted"] += Decimal(row.amount or 0) * Decimal(row.probability or 0) / 100
        bucket["count"] += 1
    return [
        {
            "month": month,
            "opportunities": int(values["count"]),
            "amount": str(values["amount"].quantize(Decimal("0.01"))),
            "weighted": str(values["weighted"].quantize(Decimal("0.01"))),
        }
        for month, values in sorted(buckets.items())
    ]


__all__ = ["router"]
