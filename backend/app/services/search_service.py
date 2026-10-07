"""Global search across the ERP, filtered by the caller's permissions.

Search results are built from server-side queries only: the caller's permission
set decides which entities are searched, so a user can never see a record they
are not allowed to view (the Flutter UI is never trusted for authorisation).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailure
from app.models.accounting import JournalEntry
from app.models.assets import Asset
from app.models.crm import Lead, Opportunity
from app.models.hr import Employee
from app.models.identity import User
from app.models.masterdata import Customer, Product, Supplier
from app.models.projects import Project
from app.models.purchasing import PurchaseOrder
from app.models.sales import SalesInvoice, SalesOrder
from app.models.service import ServiceRequest, Ticket, WorkOrder


@dataclass(slots=True)
class SearchTarget:
    """One searchable entity: how to query it and how to render a hit."""

    key: str
    label: str
    module: str
    entity: str
    model: Any
    number_field: str
    title_field: str
    subtitle_field: str | None = None
    extra_fields: tuple[str, ...] = ()
    status_field: str = "status"


SEARCH_TARGETS: tuple[SearchTarget, ...] = (
    SearchTarget("customer", "Customers", "crm", "customer", Customer, "code", "name", "contact_person", ("phone", "email")),
    SearchTarget("supplier", "Suppliers", "suppliers", "supplier", Supplier, "code", "name", "contact_person", ("phone", "email")),
    SearchTarget("product", "Items", "inventory", "product", Product, "sku", "name", "barcode", ("sales_price", "barcode")),
    SearchTarget("sales_invoice", "Sales invoices", "sales", "sales_invoice", SalesInvoice, "document_no", "document_no", "reference", ("total_amount", "currency_code")),
    SearchTarget("sales_order", "Sales orders", "sales", "sales_order", SalesOrder, "document_no", "document_no", "reference", ("total_amount", "currency_code")),
    SearchTarget("purchase_order", "Purchase orders", "purchasing", "purchase_order", PurchaseOrder, "document_no", "document_no", "supplier_reference", ("total_amount", "currency_code")),
    SearchTarget("journal_entry", "Journal entries", "accounting", "journal_entry", JournalEntry, "entry_no", "description", None, ("total_debit",)),
    SearchTarget("employee", "Employees", "hr", "employee", Employee, "employee_no", "first_name", "last_name", ("job_title", "email")),
    SearchTarget("project", "Projects", "projects", "project", Project, "project_no", "name", "description", ("status",)),
    SearchTarget("asset", "Fixed assets", "assets", "asset", Asset, "asset_no", "name", "serial_number", ("status",)),
    SearchTarget("work_order", "Work orders", "service", "work_order", WorkOrder, "document_no", "document_no", "problem_description", ("status",)),
    SearchTarget("ticket", "Tickets", "service", "ticket", Ticket, "ticket_no", "subject", "description", ("status",)),
    SearchTarget("service_request", "Service requests", "service", "service_request", ServiceRequest, "request_no", "subject", "description", ("status",)),
    SearchTarget("lead", "Leads", "crm", "lead", Lead, "lead_no", "company_name", "contact_name", ("status", "email")),
    SearchTarget("opportunity", "Opportunities", "crm", "opportunity", Opportunity, "opportunity_no", "name", "notes", ("status", "amount")),
)


class SearchService:
    """Permission-aware global search plus per-entity quick search."""

    def __init__(
        self,
        db: Session,
        company_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        permissions: Any | None = None,
    ) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.permissions = permissions

    # --------------------------------------------------------------- internals
    def caller_permissions(self) -> Any:
        if self.permissions is not None:
            return self.permissions
        if self.user_id is None:
            return None
        from app.services.auth_service import AuthService

        user = self.db.get(User, self.user_id)
        if user is None:
            return None
        self.permissions = AuthService(self.db).resolve_permissions(user, self.company_id)
        return self.permissions

    def searchable_targets(self) -> list[SearchTarget]:
        permissions = self.caller_permissions()
        if permissions is None:
            return list(SEARCH_TARGETS)
        allowed: list[SearchTarget] = []
        for target in SEARCH_TARGETS:
            if permissions.any_of(
                f"{target.module}.{target.entity}.view",
                f"{target.module}.{target.entity}.*",
                "*",
            ):
                allowed.append(target)
        return allowed

    def _base_conditions(self, target: SearchTarget, needle: str) -> list[Any]:
        columns = [getattr(target.model, target.number_field, None), getattr(target.model, target.title_field, None)]
        if target.subtitle_field:
            columns.append(getattr(target.model, target.subtitle_field, None))
        for field in target.extra_fields:
            model_field = getattr(target.model, "barcode" if field == "barcode" else field, None)
            if model_field is not None:
                columns.append(model_field)
        conditions = []
        for column in columns:
            if column is None:
                continue
            try:
                conditions.append(column.ilike(needle))
            except AttributeError:  # pragma: no cover - non text columns
                continue
        return conditions

    def _statement(self, target: SearchTarget, needle: str, limit: int) -> Select[Any]:
        stmt = select(target.model).where(target.model.company_id == self.company_id)
        if hasattr(target.model, "deleted_at"):
            stmt = stmt.where(target.model.deleted_at.is_(None))
        conditions = self._base_conditions(target, needle)
        if conditions:
            stmt = stmt.where(or_(*conditions))
        return stmt.limit(limit)

    def _render(self, target: SearchTarget, record: Any) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        for field in target.extra_fields:
            extra[field] = str(getattr(record, field, "") or "")
        subtitle = getattr(record, target.subtitle_field, None) if target.subtitle_field else None
        status = getattr(record, target.status_field, None) if hasattr(record, target.status_field) else None
        return {
            "entity": target.key,
            "label": target.label,
            "module": target.module,
            "id": str(record.id),
            "number": getattr(record, target.number_field, None),
            "title": getattr(record, target.title_field, None),
            "subtitle": subtitle,
            "status": status,
            "extra": extra,
        }

    # -------------------------------------------------------------------- API
    def search(
        self,
        query: str,
        *,
        limit_per_entity: int = 5,
        entities: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if len(query) < 2:
            raise ValidationFailure("Enter at least two characters to search")
        needle = f"%{query}%"
        targets = self.searchable_targets()
        if entities:
            wanted = {str(item) for item in entities}
            targets = [target for target in targets if target.key in wanted]
        groups: list[dict[str, Any]] = []
        total = 0
        for target in targets:
            records = self.db.execute(self._statement(target, needle, limit_per_entity)).scalars().all()
            if not records:
                continue
            hits = [self._render(target, record) for record in records]
            total += len(hits)
            groups.append({"entity": target.key, "label": target.label, "module": target.module, "count": len(hits), "results": hits})
        return {"query": query, "total": total, "groups": groups}

    def quick_search(self, entity: str, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Single-entity typeahead used by pickers (customers, items...)."""
        target = next((item for item in SEARCH_TARGETS if item.key == entity), None)
        if target is None:
            raise ValidationFailure(f"'{entity}' is not searchable", entities=[item.key for item in SEARCH_TARGETS])
        permissions = self.caller_permissions()
        if permissions is not None and not permissions.any_of(
            f"{target.module}.{target.entity}.view", f"{target.module}.{target.entity}.*", "*"
        ):
            raise ValidationFailure(f"You are not allowed to search {target.label}")
        needle = f"%{(query or '').strip()}%"
        records = self.db.execute(self._statement(target, needle, limit)).scalars().all()
        return [self._render(target, record) for record in records]

    def recent(self, *, entity: str, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent records of an entity the caller may view."""
        target = next((item for item in SEARCH_TARGETS if item.key == entity), None)
        if target is None:
            raise ValidationFailure(f"'{entity}' is not searchable")
        stmt = select(target.model).where(target.model.company_id == self.company_id)
        if hasattr(target.model, "deleted_at"):
            stmt = stmt.where(target.model.deleted_at.is_(None))
        order_column = getattr(target.model, "created_at", None)
        if order_column is not None:
            stmt = stmt.order_by(order_column.desc())
        records = self.db.execute(stmt.limit(limit)).scalars().all()
        return [self._render(target, record) for record in records]

    def available_entities(self) -> Iterable[dict[str, str]]:
        return [{"entity": target.key, "label": target.label, "module": target.module} for target in self.searchable_targets()]
