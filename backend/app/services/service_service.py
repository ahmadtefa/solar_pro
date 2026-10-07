"""Field service: requests, tickets, work orders, contracts, warranty and technicians."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import (
    AuditAction,
    DocumentStatus,
    MovementType,
    Priority,
    ServiceContractStatus,
    TicketStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.hr import Employee
from app.models.masterdata import Customer
from app.models.service import (
    ServiceContract,
    ServiceContractAsset,
    ServiceRequest,
    TechnicianSchedule,
    Ticket,
    TicketMessage,
    Warranty,
    WorkOrder,
    WorkOrderLabor,
    WorkOrderPart,
)
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.inventory_service import InventoryService, StockMove
from app.services.numbering_service import NumberingService
from app.services.posting_service import EntryLine, money, quantity

ZERO = Decimal("0")
#: First-response / resolution SLA targets (minutes) per priority.
SLA_TARGETS: dict[str, tuple[int, int]] = {
    Priority.URGENT.value: (30, 240),
    Priority.HIGH.value: (60, 480),
    Priority.NORMAL.value: (240, 1440),
    Priority.LOW.value: (480, 2880),
}


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


class ServiceRequestService:
    """Customer service requests: capture, triage, escalation to tickets/work orders."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ----------------------------------------------------------------- helpers
    def get(self, request_id: uuid.UUID | str) -> ServiceRequest:
        identifier = as_uuid(request_id)
        request = self.db.execute(
            select(ServiceRequest).where(
                ServiceRequest.company_id == self.company_id, ServiceRequest.id == identifier
            )
        ).scalars().first()
        if request is None:
            raise NotFoundError("Service request not found", id=str(request_id))
        return request

    def create(self, payload: dict[str, Any]) -> ServiceRequest:
        customer_id = as_uuid(payload["customer_id"])
        customer = self.db.execute(
            select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
        ).scalars().first()
        if customer is None:
            raise NotFoundError("Customer not found", id=str(customer_id))
        branch_id = as_uuid(payload.get("branch_id"))
        contract_id = as_uuid(payload.get("contract_id"))
        request = ServiceRequest(
            company_id=self.company_id,
            request_no=NumberingService(self.db, self.company_id).next_number(
                "service_request", branch_id=branch_id
            ),
            customer_id=customer.id,
            contact_id=as_uuid(payload.get("contact_id")),
            asset_id=as_uuid(payload.get("asset_id")),
            contract_id=contract_id,
            project_id=as_uuid(payload.get("project_id")),
            site_address=payload.get("site_address") or customer.address_line1,
            request_type=payload.get("request_type", "general"),
            subject=payload["subject"],
            description=payload.get("description"),
            priority=payload.get("priority", Priority.NORMAL.value),
            status=TicketStatus.NEW.value,
            reported_by=payload.get("reported_by"),
            reported_phone=payload.get("reported_phone") or customer.phone,
            reported_at=payload.get("reported_at") or datetime.now(UTC),
            preferred_visit_date=payload.get("preferred_visit_date"),
            is_under_warranty=bool(payload.get("is_under_warranty", False)),
            is_billable=self._resolve_billable(payload, customer, contract_id),
            assigned_to_id=as_uuid(payload.get("assigned_to_id")),
            branch_id=branch_id,
            tags=payload.get("tags") or [],
        )
        request.sla_due_at = self.sla_due_at(request.priority, request.reported_at)
        self.db.add(request)
        self.db.flush()
        self.audit.log_create(request, entity_type="service_request", label=request.request_no)
        return request

    def _resolve_billable(
        self, payload: dict[str, Any], customer: Customer, contract_id: uuid.UUID | None
    ) -> bool:
        if "is_billable" in payload:
            return bool(payload["is_billable"])
        if contract_id is not None:
            contract = self.db.get(ServiceContract, contract_id)
            if contract is not None and contract.status == ServiceContractStatus.ACTIVE.value:
                # A live contract with remaining included visits covers this call.
                if int(contract.visits_included or 0) > int(contract.visits_used or 0):
                    return False
        return True

    @staticmethod
    def sla_due_at(priority: str, reported_at: datetime | None) -> datetime:
        base = reported_at or datetime.now(UTC)
        _, resolution_minutes = SLA_TARGETS.get(priority, SLA_TARGETS[Priority.NORMAL.value])
        return base + timedelta(minutes=resolution_minutes)

    # -------------------------------------------------------------- lifecycle
    def list(
        self,
        *,
        status: str | None = None,
        customer_id: uuid.UUID | str | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[ServiceRequest]:
        stmt = select(ServiceRequest).where(ServiceRequest.company_id == self.company_id)
        if status:
            stmt = stmt.where(ServiceRequest.status == status)
        if customer_id:
            stmt = stmt.where(ServiceRequest.customer_id == as_uuid(customer_id))
        if open_only:
            stmt = stmt.where(
                ServiceRequest.status.notin_(
                    {TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value, TicketStatus.CANCELLED.value}
                )
            )
        stmt = stmt.order_by(ServiceRequest.request_no.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def assign(self, request_id: uuid.UUID | str, user_id: uuid.UUID | str) -> ServiceRequest:
        request = self.get(request_id)
        request.assigned_to_id = as_uuid(user_id)
        request.status = TicketStatus.ASSIGNED.value
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, request, entity_type="service_request", remarks="assigned")
        return request

    def close(self, request_id: uuid.UUID | str, *, resolution: str | None = None) -> ServiceRequest:
        request = self.get(request_id)
        request.status = TicketStatus.CLOSED.value
        request.closed_at = datetime.now(UTC)
        request.resolution = resolution or request.resolution
        self.db.flush()
        self.audit.log_action(AuditAction.CLOSE, request, entity_type="service_request", label=request.request_no)
        return request

    def create_ticket(self, request_id: uuid.UUID | str, payload: dict[str, Any] | None = None) -> Ticket:
        request = self.get(request_id)
        payload = payload or {}
        ticket = TicketService(self.db, self.company_id, user_id=self.user_id).create(
            {
                "customer_id": str(request.customer_id),
                "service_request_id": str(request.id),
                "asset_id": str(request.asset_id) if request.asset_id else None,
                "project_id": str(request.project_id) if request.project_id else None,
                "subject": payload.get("subject") or request.subject,
                "description": payload.get("description") or request.description,
                "category": payload.get("category") or request.request_type,
                "priority": payload.get("priority") or request.priority,
                "severity": payload.get("severity"),
                "channel": payload.get("channel", "phone"),
                "assigned_to_id": payload.get("assigned_to_id")
                or (str(request.assigned_to_id) if request.assigned_to_id else None),
                "branch_id": str(request.branch_id) if request.branch_id else None,
                "tags": request.tags,
            }
        )
        request.status = TicketStatus.IN_PROGRESS.value
        self.db.flush()
        return ticket

    def create_work_order(self, request_id: uuid.UUID | str, payload: dict[str, Any] | None = None) -> WorkOrder:
        request = self.get(request_id)
        payload = payload or {}
        work_order = WorkOrderService(self.db, self.company_id, user_id=self.user_id).create(
            {
                "customer_id": str(request.customer_id),
                "work_order_type": payload.get("work_order_type", "repair"),
                "service_request_id": str(request.id),
                "contract_id": str(request.contract_id) if request.contract_id else None,
                "asset_id": str(request.asset_id) if request.asset_id else None,
                "project_id": str(request.project_id) if request.project_id else None,
                "branch_id": str(request.branch_id) if request.branch_id else None,
                "technician_id": payload.get("technician_id"),
                "scheduled_date": payload.get("scheduled_date"),
                "priority": payload.get("priority") or request.priority,
                "site_address": request.site_address,
                "problem_description": payload.get("problem_description") or request.description,
                "is_billable": request.is_billable,
                "warranty_claim": request.is_under_warranty,
                "parts": payload.get("parts") or [],
                "labour": payload.get("labour") or [],
            }
        )
        request.status = TicketStatus.IN_PROGRESS.value
        self.db.flush()
        return work_order


class TicketService:
    """Support ticket with a conversation thread and SLA tracking."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def get(self, ticket_id: uuid.UUID | str) -> Ticket:
        identifier = as_uuid(ticket_id)
        ticket = self.db.execute(
            select(Ticket).where(Ticket.company_id == self.company_id, Ticket.id == identifier)
        ).scalars().first()
        if ticket is None:
            raise NotFoundError("Ticket not found", id=str(ticket_id))
        return ticket

    def create(self, payload: dict[str, Any]) -> Ticket:
        customer_id = as_uuid(payload["customer_id"])
        customer = self.db.execute(
            select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
        ).scalars().first()
        if customer is None:
            raise NotFoundError("Customer not found", id=str(customer_id))
        ticket = Ticket(
            company_id=self.company_id,
            ticket_no=NumberingService(self.db, self.company_id).next_number(
                "ticket", branch_id=as_uuid(payload.get("branch_id"))
            ),
            customer_id=customer.id,
            service_request_id=as_uuid(payload.get("service_request_id")),
            asset_id=as_uuid(payload.get("asset_id")),
            project_id=as_uuid(payload.get("project_id")),
            subject=payload["subject"],
            description=payload.get("description"),
            category=payload.get("category", "general"),
            priority=payload.get("priority", Priority.NORMAL.value),
            severity=payload.get("severity"),
            status=TicketStatus.NEW.value,
            channel=payload.get("channel", "phone"),
            assigned_to_id=as_uuid(payload.get("assigned_to_id")),
            assigned_team=payload.get("assigned_team"),
            branch_id=as_uuid(payload.get("branch_id")),
            tags=payload.get("tags") or [],
        )
        response_target, resolution_target = SLA_TARGETS.get(
            ticket.priority, SLA_TARGETS[Priority.NORMAL.value]
        )
        ticket.sla_response_minutes = response_target
        ticket.sla_resolution_minutes = resolution_target
        self.db.add(ticket)
        self.db.flush()
        if payload.get("message"):
            self.add_message(
                ticket.id,
                {"message": payload["message"], "direction": payload.get("direction", "inbound")},
            )
        self.audit.log_create(ticket, entity_type="ticket", label=ticket.ticket_no)
        return ticket

    def list(
        self,
        *,
        status: str | None = None,
        assigned_to_id: uuid.UUID | str | None = None,
        breached_only: bool = False,
        limit: int = 200,
    ) -> list[Ticket]:
        stmt = select(Ticket).where(Ticket.company_id == self.company_id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        if assigned_to_id:
            stmt = stmt.where(Ticket.assigned_to_id == as_uuid(assigned_to_id))
        if breached_only:
            stmt = stmt.where(Ticket.is_sla_breached.is_(True))
        stmt = stmt.order_by(Ticket.ticket_no.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def add_message(self, ticket_id: uuid.UUID | str, payload: dict[str, Any]) -> TicketMessage:
        ticket = self.get(ticket_id)
        message = TicketMessage(
            company_id=self.company_id,
            ticket_id=ticket.id,
            author_id=as_uuid(payload.get("author_id")) or self.user_id,
            author_name=payload.get("author_name"),
            direction=payload.get("direction", "outbound"),
            message=payload["message"],
            is_internal=bool(payload.get("is_internal", False)),
            attachment_count=int(payload.get("attachment_count") or 0),
        )
        self.db.add(message)
        if message.direction == "outbound" and ticket.first_response_at is None:
            ticket.first_response_at = datetime.now(UTC)
            if ticket.sla_response_minutes:
                elapsed = (
                    ticket.first_response_at - (ticket.created_at or ticket.first_response_at)
                ).total_seconds() / 60
                if elapsed > ticket.sla_response_minutes:
                    ticket.is_sla_breached = True
        if ticket.status == TicketStatus.NEW.value:
            ticket.status = TicketStatus.OPEN.value
        self.db.flush()
        return message

    def assign(self, ticket_id: uuid.UUID | str, user_id: uuid.UUID | str) -> Ticket:
        ticket = self.get(ticket_id)
        ticket.assigned_to_id = as_uuid(user_id)
        ticket.status = TicketStatus.ASSIGNED.value
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, ticket, entity_type="ticket", remarks="assigned")
        return ticket

    def set_status(self, ticket_id: uuid.UUID | str, status: str) -> Ticket:
        if status not in {member.value for member in TicketStatus}:
            raise ValidationFailure(f"Unknown ticket status '{status}'")
        ticket = self.get(ticket_id)
        ticket.status = status
        if status == TicketStatus.RESOLVED.value:
            ticket.resolved_at = datetime.now(UTC)
            self._check_resolution_sla(ticket)
        elif status == TicketStatus.CLOSED.value:
            ticket.closed_at = datetime.now(UTC)
            if ticket.resolved_at is None:
                ticket.resolved_at = ticket.closed_at
                self._check_resolution_sla(ticket)
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, ticket, entity_type="ticket", remarks=f"status={status}")
        return ticket

    def _check_resolution_sla(self, ticket: Ticket) -> None:
        if not ticket.sla_resolution_minutes:
            return
        reference = ticket.created_at or ticket.resolved_at
        elapsed = (ticket.resolved_at - reference).total_seconds() / 60
        if elapsed > ticket.sla_resolution_minutes:
            ticket.is_sla_breached = True

    def resolve(
        self, ticket_id: uuid.UUID | str, *, resolution: str, satisfaction_score: int | None = None
    ) -> Ticket:
        ticket = self.set_status(ticket_id, TicketStatus.RESOLVED.value)
        ticket.resolution = resolution
        if satisfaction_score is not None:
            if not 1 <= int(satisfaction_score) <= 5:
                raise ValidationFailure("The satisfaction score must be between 1 and 5")
            ticket.satisfaction_score = int(satisfaction_score)
        self.db.flush()
        return ticket

    def close(self, ticket_id: uuid.UUID | str) -> Ticket:
        return self.set_status(ticket_id, TicketStatus.CLOSED.value)

    def queue(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Open tickets ordered by SLA pressure (breached first, then priority)."""
        pending = (
            self.db.execute(
                select(Ticket)
                .where(
                    Ticket.company_id == self.company_id,
                    Ticket.status.in_(
                        {
                            TicketStatus.NEW.value,
                            TicketStatus.OPEN.value,
                            TicketStatus.ASSIGNED.value,
                            TicketStatus.IN_PROGRESS.value,
                            TicketStatus.WAITING_CUSTOMER.value,
                            TicketStatus.WAITING_PARTS.value,
                        }
                    ),
                )
                .order_by(Ticket.is_sla_breached.desc(), Ticket.created_at)
                .limit(limit)
            ).scalars().all()
        )
        now = datetime.now(UTC)
        rows = []
        for ticket in pending:
            target = None
            if ticket.sla_resolution_minutes and ticket.created_at is not None:
                created = ticket.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                target = created + timedelta(minutes=ticket.sla_resolution_minutes)
            rows.append(
                {
                    "ticket": ticket.ticket_no,
                    "subject": ticket.subject,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "assigned_to_id": str(ticket.assigned_to_id) if ticket.assigned_to_id else None,
                    "sla_due_at": target.isoformat() if target else None,
                    "minutes_remaining": int((target - now).total_seconds() / 60) if target else None,
                    "breached": bool(ticket.is_sla_breached) or (target is not None and now > target),
                }
            )
        return rows


class ServiceContractService(BaseDocumentService):
    """Recurring maintenance contracts (AMC): coverage, visits and billing."""

    document_type = "service_contract"
    model = ServiceContract
    line_model = None
    line_relationship = "assets"
    permission_entity = "service_contract"
    permission_module = "service"
    requires_lines = False

    def create(self, payload: dict[str, Any]) -> ServiceContract:
        customer_id = as_uuid(payload["customer_id"])
        customer = self.db.execute(
            select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
        ).scalars().first()
        if customer is None:
            raise NotFoundError("Customer not found", id=str(customer_id))
        start_date = payload.get("start_date") or date.today()
        end_date = payload.get("end_date")
        if end_date is None:
            end_date = start_date + timedelta(days=365)
        if end_date < start_date:
            raise ValidationFailure("The contract end date cannot be before the start date")
        contract = ServiceContract(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=payload.get("document_date") or start_date,
            customer_id=customer.id,
            contract_type=payload.get("contract_type", "maintenance"),
            start_date=start_date,
            end_date=end_date,
            billing_frequency=payload.get("billing_frequency", "monthly"),
            contract_value=money(payload.get("contract_value")),
            annual_value=money(payload.get("annual_value")),
            visits_included=int(payload.get("visits_included") or 0),
            response_hours=int(payload.get("response_hours") or 24),
            resolution_hours=int(payload.get("resolution_hours") or 72),
            parts_discount_percent=_decimal(payload.get("parts_discount_percent")),
            labour_included=bool(payload.get("labour_included", True)),
            auto_renew=bool(payload.get("auto_renew", False)),
            renewal_notice_days=int(payload.get("renewal_notice_days") or 30),
            status=ServiceContractStatus.DRAFT.value,
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            notes=payload.get("notes"),
            internal_notes=payload.get("internal_notes"),
            terms_and_conditions=payload.get("terms_and_conditions"),
            created_by_id=self.user_id,
        )
        if contract.annual_value == 0 and contract.contract_value:
            contract.annual_value = money(
                money(contract.contract_value) * Decimal("365") / Decimal(max((end_date - start_date).days, 1))
            )
        self.db.add(contract)
        self.db.flush()
        for asset in payload.get("assets") or []:
            self.add_asset(contract.id, asset)
        self.audit.log_create(contract, entity_type="service_contract", label=contract.document_no)
        return contract

    def add_asset(self, contract_id: uuid.UUID | str, payload: dict[str, Any]) -> ServiceContractAsset:
        contract = self.get_document(as_uuid(contract_id))
        asset_id = as_uuid(payload["asset_id"])
        row = ServiceContractAsset(
            company_id=self.company_id,
            contract_id=contract.id,
            asset_id=asset_id,
            serial_number=payload.get("serial_number"),
            location=payload.get("location"),
            coverage_notes=payload.get("coverage_notes"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def activate(self, contract_id: uuid.UUID | str, *, signed_by: str | None = None) -> ServiceContract:
        contract = self.get_document(as_uuid(contract_id))
        if contract.status not in {ServiceContractStatus.DRAFT.value, ServiceContractStatus.SUSPENDED.value}:
            raise BusinessRuleError("Only draft or suspended contracts can be activated")
        contract.status = ServiceContractStatus.ACTIVE.value
        if signed_by:
            contract.signed_by_customer = signed_by
            contract.signed_at = datetime.now(UTC)
        self.db.flush()
        self.audit.log_action(AuditAction.APPROVE, contract, entity_type="service_contract", remarks="activated")
        return contract

    def record_visit(self, contract_id: uuid.UUID | str, *, note: str | None = None) -> ServiceContract:
        contract = self.get_document(as_uuid(contract_id))
        if contract.status != ServiceContractStatus.ACTIVE.value:
            raise BusinessRuleError("Only active contracts cover visits")
        if contract.visits_included and contract.visits_used >= contract.visits_included:
            raise BusinessRuleError(
                "All visits included in this contract were already used",
                included=contract.visits_included,
                used=contract.visits_used,
            )
        contract.visits_used = int(contract.visits_used or 0) + 1
        extra = dict(contract.extra_data or {})
        history = list(extra.get("visits") or [])
        history.append({"date": date.today().isoformat(), "note": note})
        extra["visits"] = history
        contract.extra_data = extra
        self.db.flush()
        return contract

    def schedule_visits(
        self, contract_id: uuid.UUID | str, *, technician_id: uuid.UUID | str | None, interval_days: int = 90
    ) -> list[TechnicianSchedule]:
        contract = self.get_document(as_uuid(contract_id))
        if contract.status != ServiceContractStatus.ACTIVE.value:
            raise BusinessRuleError("Only active contracts can be scheduled")
        rows: list[TechnicianSchedule] = []
        cursor = max(contract.start_date, date.today())
        while cursor <= contract.end_date:
            rows.append(
                TechnicianScheduleService(self.db, self.company_id, user_id=self.user_id).schedule(
                    {
                        "employee_id": technician_id,
                        "schedule_date": cursor,
                        "work_order_id": None,
                        "skills": contract.contract_type,
                        "notes": f"Planned maintenance visit for {contract.document_no}",
                    }
                )
            )
            cursor = cursor + timedelta(days=interval_days)
        return rows

    def expire_due_contracts(self, *, as_of: date | None = None) -> list[ServiceContract]:
        today = as_of or date.today()
        contracts = self.db.execute(
            select(ServiceContract).where(
                ServiceContract.company_id == self.company_id,
                ServiceContract.status == ServiceContractStatus.ACTIVE.value,
                ServiceContract.end_date < today,
            )
        ).scalars().all()
        for contract in contracts:
            contract.status = ServiceContractStatus.EXPIRED.value
            if contract.auto_renew:
                contract.start_date = today
                contract.end_date = today + timedelta(days=365)
                contract.visits_used = 0
                contract.status = ServiceContractStatus.ACTIVE.value
            self.audit.log_action(
                AuditAction.UPDATE, contract, entity_type="service_contract", remarks="expiry run"
            )
        self.db.flush()
        return list(contracts)

    def build_journal_lines(self, document: ServiceContract, inventory_result: Any = None) -> list[EntryLine]:
        """Contracts are invoiced, not posted; revenue is recognised per invoice."""
        return []


class WorkOrderService(BaseDocumentService):
    """Field work orders: scheduling, parts issue, labour, sign-off and invoicing."""

    document_type = "work_order"
    model = WorkOrder
    line_model = WorkOrderPart
    line_relationship = "parts"
    permission_entity = "work_order"
    permission_module = "service"
    requires_lines = False

    # ------------------------------------------------------------------ create
    def create(self, payload: dict[str, Any]) -> WorkOrder:
        customer_id = as_uuid(payload["customer_id"])
        customer = self.db.execute(
            select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
        ).scalars().first()
        if customer is None:
            raise NotFoundError("Customer not found", id=str(customer_id))
        contract_id = as_uuid(payload.get("contract_id"))
        contract = self.db.get(ServiceContract, contract_id) if contract_id else None
        work_order = WorkOrder(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=payload.get("document_date") or date.today(),
            customer_id=customer.id,
            work_order_type=payload.get("work_order_type", "repair"),
            service_request_id=as_uuid(payload.get("service_request_id")),
            ticket_id=as_uuid(payload.get("ticket_id")),
            contract_id=contract_id,
            asset_id=as_uuid(payload.get("asset_id")),
            project_id=as_uuid(payload.get("project_id")),
            sales_order_id=as_uuid(payload.get("sales_order_id")),
            technician_id=self._resolve_employee(payload.get("technician_id")),
            team_ids=payload.get("team_ids") or [],
            scheduled_date=payload.get("scheduled_date"),
            priority=payload.get("priority", Priority.NORMAL.value),
            site_address=payload.get("site_address") or customer.address_line1,
            latitude=_decimal(payload.get("latitude")) if payload.get("latitude") else None,
            longitude=_decimal(payload.get("longitude")) if payload.get("longitude") else None,
            problem_description=payload.get("problem_description"),
            diagnosis=payload.get("diagnosis"),
            is_billable=bool(payload.get("is_billable", True)),
            warranty_claim=bool(payload.get("warranty_claim", False)),
            status=DocumentStatus.DRAFT.value,
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            notes=payload.get("notes"),
            internal_notes=payload.get("internal_notes"),
            terms_and_conditions=payload.get("terms_and_conditions"),
            created_by_id=self.user_id,
        )
        if contract is not None:
            work_order.parts_amount = ZERO
            extra = dict(work_order.extra_data or {})
            extra["parts_discount_percent"] = str(money(contract.parts_discount_percent))
            extra["labour_included"] = bool(contract.labour_included)
            work_order.extra_data = extra
        self.db.add(work_order)
        self.db.flush()
        for part in payload.get("parts") or []:
            self.add_part(work_order.id, part)
        for labour in payload.get("labour") or []:
            self.add_labour(work_order.id, labour)
        self._recalculate(work_order)
        self.audit.log_create(work_order, entity_type="work_order", label=work_order.document_no)
        return work_order

    def _resolve_employee(self, value: uuid.UUID | str | None) -> uuid.UUID | None:
        identifier = as_uuid(value)
        if identifier is None:
            return None
        employee = self.db.get(Employee, identifier)
        if employee is None:
            raise NotFoundError("Technician (employee) not found", id=str(identifier))
        return employee.id

    # ------------------------------------------------------------------- lines
    def add_part(self, work_order_id: uuid.UUID | str, payload: dict[str, Any]) -> WorkOrderPart:
        work_order = self.get_document(as_uuid(work_order_id))
        self.ensure_editable(work_order)
        inventory = InventoryService(self.db, self.company_id)
        product = inventory.get_product(as_uuid(payload["product_id"]))
        qty = quantity(payload.get("quantity"))
        if qty <= 0:
            raise ValidationFailure("The part quantity must be greater than zero")
        discount = _decimal(payload.get("discount_percent"))
        unit_price = money(payload.get("unit_price") or product.sales_price)
        unit_cost = money(payload.get("unit_cost") or inventory.average_cost(product.id))
        if unit_cost == 0:
            unit_cost = money(product.cost_price or product.purchase_price)
        net = money(unit_price * qty * (Decimal("1") - discount / Decimal("100")))
        is_warranty = bool(payload.get("is_under_warranty", work_order.warranty_claim))
        if is_warranty:
            net = ZERO
        row = WorkOrderPart(
            company_id=self.company_id,
            work_order_id=work_order.id,
            sequence_no=int(payload.get("sequence_no") or len(work_order.parts) + 1),
            product_id=product.id,
            description=payload.get("description") or product.name,
            unit_id=as_uuid(payload.get("unit_id")) or product.unit_id,
            quantity=qty,
            unit_price=unit_price,
            unit_cost=unit_cost,
            discount_percent=discount,
            line_total=net,
            warehouse_id=inventory.require_warehouse(
                as_uuid(payload.get("warehouse_id"))
                or work_order.warehouse_id
                or product.default_warehouse_id
            ),
            is_under_warranty=is_warranty,
        )
        self.db.add(row)
        work_order.parts.append(row)
        self.db.flush()
        self._recalculate(work_order)
        return row

    def add_labour(self, work_order_id: uuid.UUID | str, payload: dict[str, Any]) -> WorkOrderLabor:
        work_order = self.get_document(as_uuid(work_order_id))
        self.ensure_editable(work_order)
        hours = quantity(payload.get("hours"))
        if hours < 0:
            raise ValidationFailure("Labour hours cannot be negative")
        overtime = quantity(payload.get("overtime_hours"))
        hourly_rate = money(payload.get("hourly_rate"))
        cost_rate = money(payload.get("cost_rate")) or hourly_rate
        is_billable = bool(payload.get("is_billable", work_order.is_billable))
        extra = dict(work_order.extra_data or {})
        if extra.get("labour_included"):
            is_billable = False
        total_hours = hours + overtime
        row = WorkOrderLabor(
            company_id=self.company_id,
            work_order_id=work_order.id,
            sequence_no=int(payload.get("sequence_no") or len(work_order.labours) + 1),
            employee_id=self._resolve_employee(payload.get("employee_id")),
            technician_name=payload.get("technician_name"),
            work_date=payload.get("work_date") or date.today(),
            hours=hours,
            overtime_hours=overtime,
            hourly_rate=hourly_rate,
            cost_rate=cost_rate,
            billable_amount=money(hourly_rate * total_hours) if is_billable else ZERO,
            cost_amount=money(cost_rate * total_hours),
            description=payload.get("description"),
            is_billable=is_billable,
        )
        self.db.add(row)
        work_order.labours.append(row)
        self.db.flush()
        self._recalculate(work_order)
        return row

    def _recalculate(self, work_order: WorkOrder) -> WorkOrder:
        parts_discount = money((work_order.extra_data or {}).get("parts_discount_percent"))
        gross_parts = sum((money(line.line_total) for line in work_order.parts), ZERO)
        if parts_discount > 0:
            gross_parts = money(gross_parts * (Decimal("1") - parts_discount / Decimal("100")))
        work_order.parts_amount = money(gross_parts)
        work_order.labour_amount = money(sum((money(line.billable_amount) for line in work_order.labours), ZERO))
        work_order.expenses_amount = money(work_order.expenses_amount)
        billable = work_order.is_billable and not work_order.warranty_claim
        base = (
            money(work_order.parts_amount + work_order.labour_amount + money(work_order.expenses_amount))
            if billable
            else ZERO
        )
        work_order.subtotal = base
        work_order.total_amount = base
        work_order.total_amount_base = money(base * money(work_order.exchange_rate or 1))
        work_order.balance_amount = money(work_order.total_amount - money(work_order.paid_amount))
        self.db.flush()
        return work_order

    # --------------------------------------------------------------- lifecycle
    def update(self, work_order_id: uuid.UUID | str, payload: dict[str, Any]) -> WorkOrder:
        work_order = self.get_document(as_uuid(work_order_id))
        self.ensure_editable(work_order)
        for field in (
            "problem_description",
            "diagnosis",
            "solution",
            "technician_notes",
            "site_address",
            "priority",
            "notes",
        ):
            if field in payload:
                setattr(work_order, field, payload[field])
        if "technician_id" in payload:
            work_order.technician_id = self._resolve_employee(payload["technician_id"])
        if "scheduled_date" in payload:
            work_order.scheduled_date = payload["scheduled_date"]
        if "work_order_type" in payload:
            work_order.work_order_type = payload["work_order_type"]
        self.db.flush()
        return work_order

    def schedule(self, work_order_id: uuid.UUID | str, *, scheduled_date: datetime, technician_id: Any) -> WorkOrder:
        work_order = self.get_document(as_uuid(work_order_id))
        if work_order.status not in {DocumentStatus.DRAFT.value, DocumentStatus.APPROVED.value}:
            raise BusinessRuleError("Only open work orders can be scheduled")
        work_order.scheduled_date = scheduled_date
        work_order.technician_id = self._resolve_employee(technician_id)
        TechnicianScheduleService(self.db, self.company_id, user_id=self.user_id).schedule(
            {
                "employee_id": str(work_order.technician_id) if work_order.technician_id else None,
                "schedule_date": scheduled_date.date() if isinstance(scheduled_date, datetime) else scheduled_date,
                "work_order_id": str(work_order.id),
                "notes": f"Scheduled visit for {work_order.document_no}",
            }
        )
        self.db.flush()
        return work_order

    def start(self, work_order_id: uuid.UUID | str) -> WorkOrder:
        work_order = self.get_document(as_uuid(work_order_id))
        if work_order.status not in {DocumentStatus.DRAFT.value, DocumentStatus.APPROVED.value}:
            raise BusinessRuleError("Only open work orders can be started")
        work_order.started_at = datetime.now(UTC)
        # The document lifecycle (submit/approve/post) stays with the shared
        # transitions; this only records the on-site progress.
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, work_order, entity_type="work_order", remarks="started on site")
        return work_order

    def complete(self, work_order_id: uuid.UUID | str, payload: dict[str, Any] | None = None) -> WorkOrder:
        payload = payload or {}
        work_order = self.get_document(as_uuid(work_order_id))
        if work_order.status not in {DocumentStatus.DRAFT.value, DocumentStatus.APPROVED.value}:
            raise BusinessRuleError("Only open work orders can be completed")
        now = datetime.now(UTC)
        work_order.completed_at = payload.get("completed_at") or now
        work_order.started_at = work_order.started_at or now
        started = work_order.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = int((work_order.completed_at - started).total_seconds() / 60)
        work_order.duration_minutes = int(payload.get("duration_minutes") or max(elapsed, 0))
        work_order.travel_minutes = int(payload.get("travel_minutes") or work_order.travel_minutes)
        for field in ("diagnosis", "solution", "technician_notes"):
            if payload.get(field):
                setattr(work_order, field, payload[field])
        if payload.get("customer_signature_name"):
            work_order.customer_signature_name = payload["customer_signature_name"]
            work_order.customer_signature_at = now
        if payload.get("customer_rating") is not None:
            work_order.customer_rating = int(payload["customer_rating"])
        if payload.get("expenses_amount") is not None:
            work_order.expenses_amount = money(payload["expenses_amount"])
        self._recalculate(work_order)
        self.db.flush()
        self.audit.log_action(
            AuditAction.UPDATE, work_order, entity_type="work_order", remarks="completed on site"
        )
        return work_order

    # ----------------------------------------------------------------- posting
    def validate_posting(self, document: WorkOrder) -> None:
        if not document.parts and not document.labours:
            raise BusinessRuleError("Add parts or labour before posting the work order")

    def apply_inventory(self, document: WorkOrder) -> Any:
        """Issue stock parts to the technician; non-stock items are skipped."""
        inventory = InventoryService(self.db, self.company_id)
        issued: list[dict[str, Any]] = []
        total_cost = ZERO
        for line in document.parts:
            if line.is_issued:
                continue
            product = inventory.get_product(line.product_id)
            if not product.track_inventory:
                line.is_issued = True
                issued.append({"line_id": line.id, "product_id": product.id, "quantity": "0", "cost": "0"})
                continue
            result = inventory.move(
                StockMove(
                    product_id=product.id,
                    warehouse_id=inventory.require_warehouse(
                        line.warehouse_id or document.warehouse_id or product.default_warehouse_id
                    ),
                    quantity=money(line.quantity),
                    movement_type=MovementType.ISSUE,
                    unit_id=line.unit_id,
                    entry_date=document.document_date,
                    reference_type="work_order",
                    reference_id=document.id,
                    reference_no=document.document_no,
                    reference_line_id=line.id,
                    notes=f"Service part for {document.document_no}",
                    allow_negative=True,
                )
            )
            line.unit_cost = result.unit_cost
            line.is_issued = True
            total_cost += result.total_cost
            issued.append(
                {
                    "line_id": line.id,
                    "product_id": product.id,
                    "quantity": str(money(line.quantity)),
                    "cost": str(money(result.total_cost)),
                }
            )
        self.db.flush()
        return {"issued": issued, "total_cost": money(total_cost)}

    def build_journal_lines(self, document: WorkOrder, inventory_result: Any = None) -> list[EntryLine]:
        """Recognise the cost of service parts; revenue is recognised on invoicing."""
        cost = money((inventory_result or {}).get("total_cost", 0))
        if cost <= 0:
            return []
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        if document.warranty_claim:
            expense_account = self.posting.resolve_account(
                "warranty_expense", document_type=self.document_type, fallback_code="6280"
            )
        else:
            expense_account = self.posting.resolve_account(
                "service_cost", document_type=self.document_type, fallback_code="5110"
            )
        return [
            EntryLine(
                account_id=expense_account.id,
                debit=cost,
                description=f"Service parts {document.document_no}",
                branch_id=document.branch_id,
                project_id=document.project_id,
            ),
            EntryLine(
                account_id=inventory_account.id,
                credit=cost,
                description=f"Service parts {document.document_no}",
                branch_id=document.branch_id,
            ),
        ]

    def after_post(self, document: WorkOrder, inventory_result: Any = None, entry: Any = None) -> None:
        document.posted_by_id = self.user_id
        document.posted_at = datetime.now(UTC)
        if document.contract_id:
            contract = self.db.get(ServiceContract, document.contract_id)
            if contract is not None and contract.status == ServiceContractStatus.ACTIVE.value:
                ServiceContractService(self.db, self.company_id, user_id=self.user_id).record_visit(
                    contract.id, note=f"Work order {document.document_no}"
                )
        if document.service_request_id:
            request = self.db.get(ServiceRequest, document.service_request_id)
            if request is not None and request.status not in {
                TicketStatus.CLOSED.value,
                TicketStatus.CANCELLED.value,
            }:
                request.status = TicketStatus.RESOLVED.value
                request.resolution = document.solution or document.diagnosis or "Completed on site"
                request.closed_at = datetime.now(UTC)
        if document.ticket_id:
            ticket = self.db.get(Ticket, document.ticket_id)
            if ticket is not None and ticket.status not in {
                TicketStatus.CLOSED.value,
                TicketStatus.CANCELLED.value,
            }:
                ticket.status = TicketStatus.RESOLVED.value
                ticket.resolved_at = datetime.now(UTC)
                ticket.resolution = document.solution or document.diagnosis
        self.db.flush()

    # ---------------------------------------------------------------- invoicing
    def invoice(
        self,
        work_order_id: uuid.UUID | str,
        payload: dict[str, Any] | None = None,
        *,
        post: bool = False,
        allow_credit_override: bool = False,
    ) -> Any:
        """Bill the work order through a sales invoice (parts, labour, expenses)."""
        from app.services.sales_service import SalesInvoiceService

        payload = payload or {}
        work_order = self.get_document(as_uuid(work_order_id))
        if work_order.is_invoiced:
            raise BusinessRuleError("This work order was already invoiced")
        if work_order.warranty_claim or not work_order.is_billable:
            raise BusinessRuleError("Warranty or non-billable work orders are not invoiced")
        if money(work_order.total_amount) <= 0:
            raise BusinessRuleError("Nothing to invoice on this work order")
        lines: list[dict[str, Any]] = []
        for line in work_order.parts:
            if money(line.line_total) <= 0:
                continue
            lines.append(
                {
                    "product_id": str(line.product_id),
                    "description": line.description,
                    "quantity": str(money(line.quantity)),
                    "unit_price": str(money(line.unit_price)),
                    "discount_percent": str(money(line.discount_percent)),
                    "warehouse_id": str(line.warehouse_id) if line.warehouse_id else None,
                }
            )
        if money(work_order.labour_amount) > 0:
            labour_product_id = payload.get("labour_product_id")
            if labour_product_id is None:
                raise ValidationFailure("Supply labour_product_id to invoice labour hours")
            lines.append(
                {
                    "product_id": str(labour_product_id),
                    "description": f"Labour for {work_order.document_no}",
                    "quantity": "1",
                    "unit_price": str(money(work_order.labour_amount)),
                }
            )
        if money(work_order.expenses_amount) > 0:
            expense_product_id = payload.get("expense_product_id") or payload.get("labour_product_id")
            if expense_product_id is None:
                raise ValidationFailure("Supply expense_product_id to invoice work order expenses")
            lines.append(
                {
                    "product_id": str(expense_product_id),
                    "description": f"Site expenses for {work_order.document_no}",
                    "quantity": "1",
                    "unit_price": str(money(work_order.expenses_amount)),
                }
            )
        invoice_service = SalesInvoiceService(self.db, self.company_id, user_id=self.user_id)
        invoice = invoice_service.create(
            {
                "customer_id": str(work_order.customer_id),
                "project_id": str(work_order.project_id) if work_order.project_id else None,
                "branch_id": str(work_order.branch_id) if work_order.branch_id else None,
                "warehouse_id": str(work_order.warehouse_id) if work_order.warehouse_id else None,
                "document_date": payload.get("document_date") or date.today(),
                "currency_code": work_order.currency_code,
                "payment_term_id": payload.get("payment_term_id"),
                "notes": f"Service work order {work_order.document_no}",
                "reference": work_order.document_no,
                "lines": lines,
            },
            allow_credit_override=allow_credit_override,
        )
        work_order.is_invoiced = True
        work_order.invoice_id = invoice.id
        if invoice.status == DocumentStatus.DRAFT.value:
            invoice.reference = work_order.document_no
        if post:
            invoice_service.approve(invoice)
            invoice_service.post(invoice)
            if work_order.contract_id:
                self._register_contract_billing(work_order, invoice)
        self.db.flush()
        self.audit.log_action(
            AuditAction.UPDATE, work_order, entity_type="work_order", remarks=f"invoiced {invoice.document_no}"
        )
        return invoice

    def _register_contract_billing(self, work_order: WorkOrder, invoice: Any) -> None:
        contract = self.db.get(ServiceContract, work_order.contract_id)
        if contract is None:
            return
        contract.invoiced_amount = money(Decimal(contract.invoiced_amount or 0) + money(invoice.total_amount))
        self.db.flush()


class WarrantyService:
    """Product / asset warranties and claim eligibility."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> Warranty:
        customer_id = as_uuid(payload["customer_id"])
        start_date = payload.get("start_date") or date.today()
        end_date = payload.get("end_date") or start_date + timedelta(days=int(payload.get("days") or 365))
        if end_date < start_date:
            raise ValidationFailure("The warranty end date cannot be before the start date")
        warranty = Warranty(
            company_id=self.company_id,
            warranty_no=NumberingService(self.db, self.company_id).next_number("warranty"),
            customer_id=customer_id,
            product_id=as_uuid(payload.get("product_id")),
            asset_id=as_uuid(payload.get("asset_id")),
            sales_invoice_id=as_uuid(payload.get("sales_invoice_id")),
            serial_number=payload.get("serial_number"),
            start_date=start_date,
            end_date=end_date,
            warranty_type=payload.get("warranty_type", "standard"),
            coverage=payload.get("coverage"),
            terms=payload.get("terms"),
            is_active=True,
            status=payload.get("status", "active"),
        )
        self.db.add(warranty)
        self.db.flush()
        self.audit.log_create(warranty, entity_type="warranty", label=warranty.warranty_no)
        return warranty

    def create_from_invoice(self, invoice_id: uuid.UUID | str, *, days: int = 365) -> list[Warranty]:
        from app.models.sales import SalesInvoice, SalesInvoiceLine

        invoice = self.db.execute(
            select(SalesInvoice).where(
                SalesInvoice.company_id == self.company_id, SalesInvoice.id == as_uuid(invoice_id)
            )
        ).scalars().first()
        if invoice is None:
            raise NotFoundError("Sales invoice not found", id=str(invoice_id))
        created: list[Warranty] = []
        lines = self.db.execute(
            select(SalesInvoiceLine).where(SalesInvoiceLine.invoice_id == invoice.id)
        ).scalars().all()
        for line in lines:
            if line.product_id is None:
                continue
            created.append(
                self.create(
                    {
                        "customer_id": str(invoice.customer_id),
                        "product_id": str(line.product_id),
                        "sales_invoice_id": str(invoice.id),
                        "start_date": invoice.document_date,
                        "days": days,
                        "warranty_type": "standard",
                        "coverage": "Manufacturer warranty",
                    }
                )
            )
        return created

    def find_active(
        self,
        *,
        customer_id: uuid.UUID | str | None = None,
        product_id: uuid.UUID | str | None = None,
        serial_number: str | None = None,
        as_of: date | None = None,
    ) -> Warranty | None:
        today = as_of or date.today()
        stmt = select(Warranty).where(
            Warranty.company_id == self.company_id,
            Warranty.is_active.is_(True),
            Warranty.start_date <= today,
            Warranty.end_date >= today,
        )
        if customer_id:
            stmt = stmt.where(Warranty.customer_id == as_uuid(customer_id))
        if product_id:
            stmt = stmt.where(Warranty.product_id == as_uuid(product_id))
        if serial_number:
            stmt = stmt.where(Warranty.serial_number == serial_number)
        stmt = stmt.order_by(Warranty.end_date.desc())
        return self.db.execute(stmt).scalars().first()

    def claim(self, warranty_id: uuid.UUID | str, *, note: str | None = None) -> Warranty:
        warranty = self.db.execute(
            select(Warranty).where(
                Warranty.company_id == self.company_id, Warranty.id == as_uuid(warranty_id)
            )
        ).scalars().first()
        if warranty is None:
            raise NotFoundError("Warranty not found", id=str(warranty_id))
        if not warranty.is_active or warranty.end_date < date.today():
            raise BusinessRuleError("This warranty is no longer active")
        warranty.claims_count = int(warranty.claims_count or 0) + 1
        warranty.last_claim_at = datetime.now(UTC)
        extra = dict(warranty.extra_data or {})
        claims = list(extra.get("claims") or [])
        claims.append({"date": date.today().isoformat(), "note": note})
        extra["claims"] = claims
        warranty.extra_data = extra
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, warranty, entity_type="warranty", remarks="claim recorded")
        return warranty

    def expire_due(self, *, as_of: date | None = None) -> int:
        today = as_of or date.today()
        warranties = self.db.execute(
            select(Warranty).where(
                Warranty.company_id == self.company_id,
                Warranty.is_active.is_(True),
                Warranty.end_date < today,
            )
        ).scalars().all()
        for warranty in warranties:
            warranty.is_active = False
            warranty.status = "expired"
        self.db.flush()
        return len(warranties)


class TechnicianScheduleService:
    """Technician scheduling and utilisation."""

    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def schedule(self, payload: dict[str, Any]) -> TechnicianSchedule:
        employee_id = as_uuid(payload.get("employee_id"))
        if employee_id is not None:
            employee = self.db.get(Employee, employee_id)
            if employee is None:
                raise NotFoundError("Technician (employee) not found", id=str(employee_id))
        slot_date = payload["schedule_date"]
        if isinstance(slot_date, datetime):
            slot_date = slot_date.date()
        # The schedule stores datetimes; accept plain times or datetimes and combine
        # them with the slot date (the same convention as HR attendance).
        start_at = self._combine(slot_date, payload.get("start_time"), default=time(9, 0))
        end_at = self._combine(slot_date, payload.get("end_time"), default=time(17, 0))
        if end_at <= start_at:
            raise ValidationFailure("The schedule end time must be after the start time")
        if employee_id is not None:
            conflict = self.db.execute(
                select(TechnicianSchedule).where(
                    TechnicianSchedule.company_id == self.company_id,
                    TechnicianSchedule.employee_id == employee_id,
                    TechnicianSchedule.schedule_date == slot_date,
                )
            ).scalars().all()
            for existing in conflict:
                if existing.start_time is None or existing.end_time is None:
                    continue
                if self._naive(existing.start_time) < end_at and start_at < self._naive(existing.end_time):
                    raise BusinessRuleError(
                        "The technician already has a visit in this time slot",
                        existing_start=str(existing.start_time),
                        existing_end=str(existing.end_time),
                    )
        row = TechnicianSchedule(
            company_id=self.company_id,
            employee_id=employee_id,
            schedule_date=slot_date,
            start_time=start_at,
            end_time=end_at,
            status=payload.get("status", "planned"),
            work_order_id=as_uuid(payload.get("work_order_id")),
            skills=payload.get("skills"),
            notes=payload.get("notes"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _naive(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if value.tzinfo is not None else value

    @classmethod
    def _combine(cls, slot_date: date, value: Any, *, default: time) -> datetime:
        """Accept a time, datetime or None and return a datetime on ``slot_date``."""
        if value is None:
            return datetime.combine(slot_date, default)
        if isinstance(value, datetime):
            if value.date() == slot_date:
                return cls._naive(value)
            return datetime.combine(slot_date, value.timetz().replace(tzinfo=None))
        if isinstance(value, time):
            return datetime.combine(slot_date, value)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return cls._combine(slot_date, parsed, default=default)
        raise ValidationFailure(f"Unsupported schedule time value: {value!r}")

    def agenda(self, *, on_date: date | None = None, employee_id: uuid.UUID | str | None = None) -> list[dict[str, Any]]:
        target = on_date or date.today()
        stmt = select(TechnicianSchedule).where(
            TechnicianSchedule.company_id == self.company_id,
            TechnicianSchedule.schedule_date == target,
        )
        if employee_id:
            stmt = stmt.where(TechnicianSchedule.employee_id == as_uuid(employee_id))
        rows = self.db.execute(stmt.order_by(TechnicianSchedule.start_time)).scalars().all()
        return [
            {
                "id": str(row.id),
                "employee_id": str(row.employee_id) if row.employee_id else None,
                "start": row.start_time.strftime("%H:%M") if row.start_time else None,
                "end": row.end_time.strftime("%H:%M") if row.end_time else None,
                "status": row.status,
                "work_order_id": str(row.work_order_id) if row.work_order_id else None,
                "notes": row.notes,
            }
            for row in rows
        ]

    def util_sation(self, *, date_from: date, date_to: date) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                TechnicianSchedule.employee_id,
                func.count(TechnicianSchedule.id),
            )
            .where(
                TechnicianSchedule.company_id == self.company_id,
                TechnicianSchedule.schedule_date >= date_from,
                TechnicianSchedule.schedule_date <= date_to,
            )
            .group_by(TechnicianSchedule.employee_id)
        ).all()
        summary = []
        for employee_id, visits in rows:
            employee = self.db.get(Employee, employee_id) if employee_id else None
            summary.append(
                {
                    "employee_id": str(employee_id) if employee_id else None,
                    "employee": employee.full_name if employee else None,
                    "visits": int(visits),
                }
            )
        return summary

    def work_order_summary(self, work_order_id: uuid.UUID | str) -> dict[str, Any]:
        work_order = self.db.execute(
            select(WorkOrder).where(
                WorkOrder.company_id == self.company_id, WorkOrder.id == as_uuid(work_order_id)
            )
        ).scalars().first()
        if work_order is None:
            raise NotFoundError("Work order not found", id=str(work_order_id))
        parts_cost = sum((money(line.unit_cost) * money(line.quantity) for line in work_order.parts), ZERO)
        labour_cost = sum((money(line.cost_amount) for line in work_order.labours), ZERO)
        return {
            "work_order": work_order.document_no,
            "status": work_order.status,
            "technician_id": str(work_order.technician_id) if work_order.technician_id else None,
            "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
            "duration_minutes": work_order.duration_minutes,
            "parts_amount": str(money(work_order.parts_amount)),
            "labour_amount": str(money(work_order.labour_amount)),
            "expenses_amount": str(money(work_order.expenses_amount)),
            "total_amount": str(money(work_order.total_amount)),
            "parts_cost": str(money(parts_cost)),
            "labour_cost": str(money(labour_cost)),
            "gross_margin": str(money(money(work_order.total_amount) - parts_cost - labour_cost)),
            "is_invoiced": work_order.is_invoiced,
            "warranty_claim": work_order.warranty_claim,
        }


__all__ = [
    "ServiceRequestService",
    "TicketService",
    "ServiceContractService",
    "WorkOrderService",
    "WarrantyService",
    "TechnicianScheduleService",
]
