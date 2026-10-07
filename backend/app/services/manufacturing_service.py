"""Manufacturing: work centers, BOMs, routings, production orders and WIP costing."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import AuditAction, MovementType, ProductionStatus
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.hr import Employee
from app.models.identity import User
from app.models.manufacturing import (
    Bom,
    BomLine,
    BomOperation,
    ProductionCostSheet,
    ProductionOperation,
    ProductionOrder,
    ProductionOrderMaterial,
    ProductionOutput,
    Routing,
    RoutingOperation,
    WorkCenter,
)
from app.services.audit_service import AuditContext, AuditService
from app.services.document_service import BaseDocumentService
from app.services.inventory_service import InventoryService, StockMove
from app.services.posting_service import EntryLine, money, quantity

ZERO = Decimal("0")


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


class WorkCenterService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    def create(self, payload: dict[str, Any]) -> WorkCenter:
        code = str(payload["code"]).strip().upper()
        if self.db.execute(
            select(WorkCenter).where(WorkCenter.company_id == self.company_id, WorkCenter.code == code)
        ).scalars().first():
            raise ConflictError(f"Work center {code} already exists")
        work_center = WorkCenter(
            company_id=self.company_id,
            code=code,
            name=payload["name"],
            name_ar=payload.get("name_ar"),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            wip_account_id=as_uuid(payload.get("wip_account_id")),
            overhead_account_id=as_uuid(payload.get("overhead_account_id")),
            capacity_per_day=_decimal(payload.get("capacity_per_day")),
            machine_hour_rate=money(payload.get("machine_hour_rate")),
            labour_hour_rate=money(payload.get("labour_hour_rate")),
            overhead_rate=money(payload.get("overhead_rate")),
            efficiency_percent=_decimal(payload.get("efficiency_percent"), "100"),
            notes=payload.get("notes"),
        )
        self.db.add(work_center)
        self.db.flush()
        self.audit.log_create(work_center, entity_type="work_center", label=work_center.code)
        return work_center

    def list(self) -> list[WorkCenter]:
        return list(
            self.db.execute(
                select(WorkCenter).where(WorkCenter.company_id == self.company_id).order_by(WorkCenter.code)
            ).scalars().all()
        )


class BomService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = AuditService(db, AuditContext(company_id=company_id, user_id=user_id))
        self.inventory = InventoryService(db, company_id)

    def create_bom(self, payload: dict[str, Any]) -> Bom:
        product_id = as_uuid(payload["product_id"])
        product = self.inventory.get_product(product_id)
        previous_version = self.db.execute(
            select(func.max(Bom.version)).where(Bom.company_id == self.company_id, Bom.product_id == product_id)
        ).scalar_one()
        version = int(payload.get("version") or (int(previous_version or 0) + 1))
        bom = Bom(
            company_id=self.company_id,
            code=payload.get("code") or f"BOM-{product.sku}-{version}",
            name=payload.get("name") or f"{product.name} BOM v{version}",
            product_id=product_id,
            version=version,
            quantity=_decimal(payload.get("quantity"), "1"),
            unit_id=as_uuid(payload.get("unit_id")) or product.unit_id,
            bom_type=payload.get("bom_type", "production"),
            routing_id=as_uuid(payload.get("routing_id")),
            is_active=bool(payload.get("is_active", True)),
            effective_from=payload.get("effective_from") or date.today(),
            effective_to=payload.get("effective_to"),
            expected_yield_percent=_decimal(payload.get("expected_yield_percent"), "100"),
            notes=payload.get("notes"),
        )
        self.db.add(bom)
        self.db.flush()
        self.set_lines(bom, payload.get("lines") or [])
        if payload.get("operations"):
            self.set_operations(bom, payload["operations"])
        self.compute_standard_cost(bom)
        self.db.flush()
        self.audit.log_create(bom, entity_type="bom", label=bom.code)
        return bom

    def set_lines(self, bom: Bom, lines: Sequence[dict[str, Any]]) -> None:
        bom.lines.clear()
        self.db.flush()
        for index, item in enumerate(lines, start=1):
            component_id = as_uuid(item["component_product_id"])
            component = self.inventory.get_product(component_id)
            unit_cost = money(item.get("unit_cost") or self.inventory.average_cost(component_id))
            if unit_cost == 0:
                unit_cost = money(component.cost_price or component.purchase_price)
            row = BomLine(
                company_id=self.company_id,
                bom_id=bom.id,
                sequence_no=int(item.get("sequence_no") or index),
                component_product_id=component_id,
                unit_id=as_uuid(item.get("unit_id")) or component.unit_id,
                quantity=_decimal(item.get("quantity")),
                scrap_percent=_decimal(item.get("scrap_percent")),
                is_optional=bool(item.get("is_optional", False)),
                is_substitute=bool(item.get("is_substitute", False)),
                substitute_product_ids=item.get("substitute_product_ids") or [],
                unit_cost=unit_cost,
                total_cost=money(unit_cost * _decimal(item.get("quantity"))),
                operation_id=as_uuid(item.get("operation_id")),
                warehouse_id=as_uuid(item.get("warehouse_id")),
                notes=item.get("notes"),
            )
            self.db.add(row)
            bom.lines.append(row)
        self.db.flush()

    def set_operations(self, bom: Bom, operations: Sequence[dict[str, Any]]) -> None:
        bom.operations.clear()
        self.db.flush()
        for index, item in enumerate(operations, start=1):
            row = BomOperation(
                company_id=self.company_id,
                bom_id=bom.id,
                sequence_no=int(item.get("sequence_no") or index),
                code=item.get("code") or f"OP-{int(item.get('sequence_no') or index):02d}",
                name=item["name"],
                work_center_id=as_uuid(item.get("work_center_id")),
                setup_minutes=_decimal(item.get("setup_minutes")),
                run_minutes_per_unit=_decimal(item.get("run_minutes_per_unit")),
                machine_hour_rate=money(item.get("machine_hour_rate")),
                labour_hour_rate=money(item.get("labour_hour_rate")),
                overhead_rate=money(item.get("overhead_rate")),
                instructions=item.get("instructions"),
            )
            self.db.add(row)
            bom.operations.append(row)
        self.db.flush()

    def compute_standard_cost(self, bom: Bom) -> Decimal:
        material = sum((money(line.total_cost) for line in bom.lines), ZERO)
        operations = ZERO
        for operation in bom.operations:
            minutes = money(operation.setup_minutes) + money(operation.run_minutes_per_unit) * money(bom.quantity)
            hours = minutes / Decimal("60")
            operations += hours * (
                money(operation.machine_hour_rate)
                + money(operation.labour_hour_rate)
                + money(operation.overhead_rate)
            )
        bom.standard_cost = money(material + operations)
        self.db.flush()
        return bom.standard_cost

    def get(self, bom_id: uuid.UUID) -> Bom:
        bom = self.db.execute(
            select(Bom).where(Bom.company_id == self.company_id, Bom.id == bom_id)
        ).scalars().first()
        if bom is None:
            raise NotFoundError("Bill of materials not found")
        return bom

    def active_bom(self, product_id: uuid.UUID) -> Bom | None:
        return self.db.execute(
            select(Bom)
            .where(
                Bom.company_id == self.company_id,
                Bom.product_id == product_id,
                Bom.is_active.is_(True),
            )
            .order_by(Bom.version.desc())
        ).scalars().first()

    def explode(self, product_id: uuid.UUID, *, quantity_value: Decimal = Decimal("1"), depth: int = 0) -> list[dict[str, Any]]:
        """Multi-level BOM explosion (recursive, cycle safe)."""
        if depth > 8:
            raise BusinessRuleError("BOM nesting is too deep; check for a circular reference")
        bom = self.active_bom(product_id)
        if bom is None:
            return []
        factor = quantity_value / (money(bom.quantity) or Decimal("1"))
        rows: list[dict[str, Any]] = []
        for line in bom.lines:
            component = self.inventory.get_product(line.component_product_id)
            required = quantity(money(line.quantity) * factor * (Decimal("1") + money(line.scrap_percent) / Decimal("100")))
            rows.append(
                {
                    "level": depth,
                    "product_id": str(component.id),
                    "sku": component.sku,
                    "name": component.name,
                    "quantity": str(required),
                    "unit_cost": str(money(line.unit_cost)),
                    "total_cost": str(money(required * money(line.unit_cost))),
                    "is_subassembly": self.active_bom(component.id) is not None,
                }
            )
            if self.active_bom(component.id) is not None:
                rows.extend(self.explode(component.id, quantity_value=required, depth=depth + 1))
        return rows

    def clone_version(self, bom_id: uuid.UUID) -> Bom:
        source = self.get(bom_id)
        payload = {
            "product_id": str(source.product_id),
            "name": f"{source.name} (rev)",
            "quantity": str(source.quantity),
            "unit_id": str(source.unit_id) if source.unit_id else None,
            "bom_type": source.bom_type,
            "expected_yield_percent": str(source.expected_yield_percent),
            "lines": [
                {
                    "component_product_id": str(line.component_product_id),
                    "quantity": str(line.quantity),
                    "scrap_percent": str(line.scrap_percent),
                    "unit_id": str(line.unit_id) if line.unit_id else None,
                    "is_optional": line.is_optional,
                }
                for line in source.lines
            ],
            "operations": [
                {
                    "name": operation.name,
                    "work_center_id": str(operation.work_center_id) if operation.work_center_id else None,
                    "setup_minutes": str(operation.setup_minutes),
                    "run_minutes_per_unit": str(operation.run_minutes_per_unit),
                }
                for operation in source.operations
            ],
        }
        return self.create_bom(payload)


class RoutingService:
    def __init__(self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id

    def create(self, payload: dict[str, Any]) -> Routing:
        routing = Routing(
            company_id=self.company_id,
            code=payload["code"],
            name=payload["name"],
            product_id=as_uuid(payload.get("product_id")),
            version=int(payload.get("version") or 1),
            notes=payload.get("notes"),
        )
        self.db.add(routing)
        self.db.flush()
        for index, item in enumerate(payload.get("operations") or [], start=1):
            self.db.add(
                RoutingOperation(
                    company_id=self.company_id,
                    routing_id=routing.id,
                    sequence_no=int(item.get("sequence_no") or index),
                    code=item.get("code") or f"OP-{int(item.get('sequence_no') or index):02d}",
                    name=item["name"],
                    work_center_id=as_uuid(item.get("work_center_id")),
                    setup_minutes=_decimal(item.get("setup_minutes")),
                    run_minutes_per_unit=_decimal(item.get("run_minutes_per_unit")),
                    teardown_minutes=_decimal(item.get("teardown_minutes")),
                    machine_hour_rate=money(item.get("machine_hour_rate")),
                    labour_hour_rate=money(item.get("labour_hour_rate")),
                    instructions=item.get("instructions"),
                    requires_quality_check=bool(item.get("requires_quality_check", False)),
                )
            )
        self.db.flush()
        return routing


class ProductionOrderService(BaseDocumentService):
    """Production orders: plan -> release -> consume -> produce -> cost -> post."""

    document_type = "production_order"
    model = ProductionOrder
    line_model = ProductionOrderMaterial
    line_relationship = "materials"
    permission_entity = "production_order"
    permission_module = "manufacturing"
    requires_lines = False

    # ------------------------------------------------------------------ create
    def create(self, payload: dict[str, Any]) -> ProductionOrder:
        product_id = as_uuid(payload["product_id"])
        product = self.inventory().get_product(product_id)
        bom = None
        if payload.get("bom_id"):
            bom = BomService(self.db, self.company_id, user_id=self.user_id).get(as_uuid(payload["bom_id"]))
        else:
            bom = BomService(self.db, self.company_id, user_id=self.user_id).active_bom(product_id)
        planned = quantity(payload.get("planned_quantity"))
        if planned <= 0:
            raise ValidationFailure("The planned quantity must be greater than zero")
        order = ProductionOrder(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            product_id=product_id,
            bom_id=bom.id if bom else None,
            routing_id=bom.routing_id if bom else as_uuid(payload.get("routing_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            wip_warehouse_id=as_uuid(payload.get("wip_warehouse_id")),
            customer_id=as_uuid(payload.get("customer_id")),
            sales_order_id=as_uuid(payload.get("sales_order_id")),
            project_id=as_uuid(payload.get("project_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            planned_quantity=planned,
            unit_id=as_uuid(payload.get("unit_id")) or product.unit_id,
            planned_start_date=payload.get("planned_start_date") or date.today(),
            planned_end_date=payload.get("planned_end_date"),
            status=ProductionStatus.DRAFT.value,
            priority=payload.get("priority", "normal"),
            supervisor_id=as_uuid(payload.get("supervisor_id")),
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(order)
        self.db.flush()
        if bom is not None:
            self._load_materials(order, bom, planned)
            self._load_operations(order, bom, planned)
        elif payload.get("materials"):
            for index, item in enumerate(payload["materials"], start=1):
                self.db.add(
                    ProductionOrderMaterial(
                        company_id=self.company_id,
                        production_order_id=order.id,
                        sequence_no=index,
                        product_id=as_uuid(item["product_id"]),
                        unit_id=as_uuid(item.get("unit_id")),
                        planned_quantity=_decimal(item.get("quantity")),
                        unit_cost=money(item.get("unit_cost")),
                        warehouse_id=as_uuid(item.get("warehouse_id")) or order.warehouse_id,
                    )
                )
            self.db.flush()
        self.audit.log_create(order, entity_type="production_order", label=order.document_no)
        return order

    def inventory(self) -> InventoryService:
        return InventoryService(self.db, self.company_id)

    def _load_materials(self, order: ProductionOrder, bom: Bom, planned: Decimal) -> None:
        factor = planned / (money(bom.quantity) or Decimal("1"))
        yield_percent = money(bom.expected_yield_percent) or Decimal("100")
        factor = factor * Decimal("100") / yield_percent
        for index, line in enumerate(bom.lines, start=1):
            unit_cost = money(line.unit_cost) or self.inventory().average_cost(line.component_product_id)
            required = quantity(
                money(line.quantity) * factor * (Decimal("1") + money(line.scrap_percent) / Decimal("100"))
            )
            self.db.add(
                ProductionOrderMaterial(
                    company_id=self.company_id,
                    production_order_id=order.id,
                    sequence_no=index,
                    product_id=line.component_product_id,
                    unit_id=line.unit_id,
                    planned_quantity=required,
                    unit_cost=unit_cost,
                    total_cost=money(required * unit_cost),
                    warehouse_id=line.warehouse_id or order.warehouse_id,
                )
            )
        self.db.flush()

    def _load_operations(self, order: ProductionOrder, bom: Bom, planned: Decimal) -> None:
        for index, operation in enumerate(bom.operations, start=1):
            planned_minutes = money(operation.setup_minutes) + money(operation.run_minutes_per_unit) * planned
            self.db.add(
                ProductionOperation(
                    company_id=self.company_id,
                    production_order_id=order.id,
                    sequence_no=index,
                    code=operation.code,
                    name=operation.name,
                    work_center_id=operation.work_center_id,
                    status="pending",
                    planned_minutes=planned_minutes,
                    setup_minutes=money(operation.setup_minutes),
                )
            )
        self.db.flush()

    # ------------------------------------------------------------- lifecycle
    def submit(self, document: Any) -> Any:  # noqa: D102 - bespoke lifecycle
        raise BusinessRuleError(
            "Production orders follow the manufacturing lifecycle "
            "(plan → release → produce → close); use those actions instead of submit."
        )

    def reject(self, document: Any, *, reason: str) -> Any:
        return self.cancel(document, reason=reason)

    def cancel(self, document: ProductionOrder, *, reason: str) -> ProductionOrder:
        if document.status == ProductionStatus.COMPLETED.value:
            raise BusinessRuleError("A completed production order cannot be cancelled")
        document.status = ProductionStatus.CANCELLED.value
        document.notes = f"{document.notes}\nCancelled: {reason}".strip() if document.notes else f"Cancelled: {reason}"
        self.db.flush()
        self.audit.log_action(AuditAction.CANCEL, document, entity_type=self.document_type, remarks=reason)
        return document

    def post(  # type: ignore[override]
        self, document: ProductionOrder, *, allow_draft: bool = False
    ) -> ProductionOrder:
        """Post the accumulated production cost (WIP → finished goods)."""
        if document.journal_entry_id:
            raise BusinessRuleError("The production order cost is already posted")
        if document.status == ProductionStatus.CANCELLED.value:
            raise BusinessRuleError("A cancelled production order cannot be posted")
        self.validate_posting(document)
        lines = self.build_journal_lines(document)
        entry = None
        if lines:
            entry = self.posting.build_entry(
                context=self._posting_context(document),
                lines=lines,
                entry_type=self.document_type,
                auto_post=True,
                user_id=self.user_id,
            )
            document.journal_entry_id = entry.id
        self.after_post(document, None, entry)
        self.db.flush()
        return document

    def plan(self, order_id: uuid.UUID) -> ProductionOrder:
        order = self.get_document(order_id)
        if order.status != ProductionStatus.DRAFT.value:
            raise BusinessRuleError("Only draft production orders can be planned")
        order.status = ProductionStatus.PLANNED.value
        self.db.flush()
        return order

    def release(self, order_id: uuid.UUID) -> ProductionOrder:
        order = self.get_document(order_id)
        if order.status not in {ProductionStatus.DRAFT.value, ProductionStatus.PLANNED.value}:
            raise BusinessRuleError("Only draft or planned orders can be released")
        if not order.materials:
            raise BusinessRuleError("The production order has no materials to consume")
        # Availability check with reservation.
        inventory = self.inventory()
        for material in order.materials:
            available = inventory.available_quantity(material.product_id, material.warehouse_id or order.warehouse_id)
            if available < money(material.planned_quantity):
                raise BusinessRuleError(
                    "Not enough stock to release the production order",
                    product_id=str(material.product_id),
                    required=str(quantity(material.planned_quantity)),
                    available=str(quantity(available)),
                )
            inventory.reserve(
                material.product_id,
                material.warehouse_id or order.warehouse_id,
                money(material.planned_quantity),
            )
        order.status = ProductionStatus.RELEASED.value
        order.actual_start_date = order.actual_start_date or datetime.now(UTC)
        self.db.flush()
        self.audit.log_action(AuditAction.UPDATE, order, entity_type="production_order", remarks="released")
        return order

    def issue_materials(
        self, order_id: uuid.UUID, *, materials: Sequence[dict[str, Any]] | None = None, issue_all: bool = True
    ) -> dict[str, Any]:
        order = self.get_document(order_id)
        if order.status not in {ProductionStatus.RELEASED.value, ProductionStatus.IN_PROGRESS.value}:
            raise BusinessRuleError("Materials can only be issued to a released order")
        inventory = self.inventory()
        targets = {uuid.as_uuid(item["material_id"]): item for item in (materials or []) if item.get("material_id")}
        issued = ZERO
        for material in order.materials:
            requested = material.planned_quantity if issue_all and not targets else None
            if targets:
                entry = targets.get(material.id)
                if entry is None:
                    continue
                requested = _decimal(entry.get("quantity"))
            outstanding = money(material.planned_quantity) - money(material.issued_quantity)
            if requested is None:
                requested = outstanding
            requested = min(money(requested), outstanding)
            if requested <= 0:
                continue
            result = inventory.move(
                StockMove(
                    product_id=material.product_id,
                    warehouse_id=material.warehouse_id or order.warehouse_id,
                    quantity=requested,
                    movement_type=MovementType.CONSUMPTION,
                    unit_id=material.unit_id,
                    entry_date=date.today(),
                    reference_type="production_order",
                    reference_id=order.id,
                    reference_no=order.document_no,
                    reference_line_id=material.id,
                    notes=f"Material issue for {order.document_no}",
                )
            )
            material.issued_quantity = quantity(money(material.issued_quantity) + requested)
            material.unit_cost = result.unit_cost
            material.total_cost = money(money(material.total_cost) + result.total_cost)
            material.is_consumed = money(material.issued_quantity) >= money(material.planned_quantity)
            issued += result.total_cost
            inventory.release_reservation(material.product_id, material.warehouse_id or order.warehouse_id, requested)
        order.material_cost = money(Decimal(order.material_cost or 0) + issued)
        order.status = ProductionStatus.IN_PROGRESS.value
        self.db.flush()
        self.audit.log_action(
            AuditAction.UPDATE, order, entity_type="production_order", remarks=f"materials issued {money(issued)}"
        )
        return {"issued_cost": str(money(issued)), "status": order.status}

    def _resolve_operator(self, operator_id: uuid.UUID | str | None) -> uuid.UUID | None:
        """``operator_id`` may be an employee id or a user id (mapped via the user)."""
        identifier = as_uuid(operator_id)
        if identifier is None:
            return None
        employee = self.db.get(Employee, identifier)
        if employee is not None:
            return employee.id
        user = self.db.get(User, identifier)
        if user is not None and getattr(user, "employee_id", None):
            return user.employee_id
        raise NotFoundError("Operator employee not found", id=str(identifier))

    def record_operation(
        self,
        order_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        actual_minutes: Decimal,
        operator_id: uuid.UUID | str | None = None,
        completion_percent: Decimal | None = None,
        quality_status: str | None = None,
    ) -> ProductionOperation:
        order = self.get_document(order_id)
        operation = self.db.execute(
            select(ProductionOperation).where(
                ProductionOperation.company_id == self.company_id,
                ProductionOperation.production_order_id == order.id,
                ProductionOperation.id == as_uuid(operation_id),
            )
        ).scalars().first()
        if operation is None:
            raise NotFoundError("Production operation not found")
        work_center = self.db.get(WorkCenter, operation.work_center_id) if operation.work_center_id else None
        hours = money(actual_minutes) / Decimal("60")
        machine_rate = _decimal(work_center.machine_hour_rate) if work_center else ZERO
        labour_rate = _decimal(work_center.labour_hour_rate) if work_center else ZERO
        overhead_rate = _decimal(work_center.overhead_rate) if work_center else ZERO
        operation.actual_minutes = money(Decimal(operation.actual_minutes or 0) + money(actual_minutes))
        operation.operator_id = self._resolve_operator(operator_id) or operation.operator_id
        operation.started_at = operation.started_at or datetime.now(UTC)
        operation.machine_cost = money(Decimal(operation.machine_cost or 0) + hours * machine_rate)
        operation.labour_cost = money(Decimal(operation.labour_cost or 0) + hours * labour_rate)
        operation.overhead_cost = money(Decimal(operation.overhead_cost or 0) + hours * overhead_rate)
        operation.quality_status = quality_status or operation.quality_status
        if completion_percent is not None:
            operation.completion_percent = _decimal(completion_percent)
        if operation.completion_percent >= 100 or (completion_percent is not None and _decimal(completion_percent) >= 100):
            operation.status = "completed"
            operation.finished_at = datetime.now(UTC)
            operation.completion_percent = Decimal("100")
        else:
            operation.status = "in_progress"
        order.labour_cost = money(
            sum((Decimal(item.labour_cost or 0) for item in order.operations), ZERO)
        )
        order.overhead_cost = money(
            sum(
                (Decimal(item.overhead_cost or 0) + Decimal(item.machine_cost or 0) for item in order.operations),
                ZERO,
            )
        )
        self.db.flush()
        return operation

    def produce(
        self,
        order_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> ProductionOutput:
        """Record finished goods (or scrap) production for a released order."""
        order = self.get_document(order_id)
        if order.status not in {ProductionStatus.RELEASED.value, ProductionStatus.IN_PROGRESS.value}:
            raise BusinessRuleError("Only released production orders can produce output")
        output_type = payload.get("output_type", "finished")
        qty = quantity(payload.get("quantity"))
        if qty <= 0:
            raise ValidationFailure("The produced quantity must be greater than zero")
        if output_type != "scrap":
            remaining = money(order.planned_quantity) - money(order.produced_quantity)
            if qty > remaining:
                raise BusinessRuleError(
                    "The produced quantity exceeds the planned quantity",
                    remaining=str(quantity(remaining)),
                )
        warehouse_id = as_uuid(payload.get("warehouse_id")) or order.warehouse_id
        unit_cost = money(payload.get("unit_cost")) or self._current_unit_cost(order)
        output = ProductionOutput(
            company_id=self.company_id,
            production_order_id=order.id,
            output_type=output_type,
            product_id=as_uuid(payload.get("product_id")) or order.product_id,
            quantity=qty,
            unit_id=as_uuid(payload.get("unit_id")) or order.unit_id,
            warehouse_id=warehouse_id,
            batch_id=as_uuid(payload.get("batch_id")),
            unit_cost=unit_cost,
            total_cost=money(unit_cost * qty),
            produced_at=payload.get("produced_at") or datetime.now(UTC),
            is_posted=bool(payload.get("post_inventory", True)),
            quality_status=payload.get("quality_status", "accepted"),
            scrap_reason=payload.get("scrap_reason"),
            notes=payload.get("notes"),
        )
        self.db.add(output)
        self.db.flush()

        if output.is_posted:
            inventory = self.inventory()
            if output_type == "scrap":
                # Scrap is a production loss taken out of the work in progress: the
                # material was already issued to the order (and charged to WIP), so
                # declaring scrap does not create another warehouse issue.  Reusable
                # scrap can be returned to stock explicitly.
                if money(order.produced_quantity) > 0:
                    raise BusinessRuleError(
                        "Declare scrap before recording the finished goods output so the "
                        "remaining production cost is capitalised at the correct unit cost."
                    )
                order.scrap_quantity = quantity(Decimal(order.scrap_quantity or 0) + qty)
                order.scrap_cost = money(Decimal(order.scrap_cost or 0) + money(output.total_cost))
                if payload.get("return_to_stock"):
                    inventory.move(
                        StockMove(
                            product_id=output.product_id,
                            warehouse_id=warehouse_id,
                            quantity=qty,
                            movement_type=MovementType.RECEIPT,
                            entry_date=output.produced_at,
                            unit_cost=unit_cost,
                            reference_type="production_output",
                            reference_id=output.id,
                            reference_no=order.document_no,
                            notes=f"Recovered scrap of {order.document_no}",
                        )
                    )
                    extra = dict(order.extra_data or {})
                    extra["scrap_stocked_value"] = str(
                        money(Decimal(extra.get("scrap_stocked_value", 0)) + money(output.total_cost))
                    )
                    order.extra_data = extra
            else:
                inventory.move(
                    StockMove(
                        product_id=output.product_id,
                        warehouse_id=warehouse_id,
                        quantity=qty,
                        movement_type=MovementType.PRODUCTION_IN,
                        entry_date=output.produced_at,
                        unit_cost=unit_cost,
                        batch_id=output.batch_id,
                        batch_number=payload.get("batch_number"),
                        expiry_date=payload.get("expiry_date"),
                        reference_type="production_output",
                        reference_id=output.id,
                        reference_no=order.document_no,
                    )
                )
                order.produced_quantity = quantity(Decimal(order.produced_quantity or 0) + qty)
                if payload.get("rework_quantity"):
                    order.rework_quantity = quantity(Decimal(order.rework_quantity or 0) + _decimal(payload["rework_quantity"]))
        order.unit_cost = self._current_unit_cost(order)
        order.total_cost = money(
            Decimal(order.material_cost or 0) + Decimal(order.labour_cost or 0) + Decimal(order.overhead_cost or 0)
        )
        order.wip_balance = money(
            order.total_cost
            - money(order.produced_quantity) * money(order.unit_cost)
            - money(order.scrap_cost)
        )
        self.db.flush()
        return output

    def _current_unit_cost(self, order: ProductionOrder) -> Decimal:
        total = money(
            Decimal(order.material_cost or 0) + Decimal(order.labour_cost or 0) + Decimal(order.overhead_cost or 0)
        )
        # Scrap is expensed/recovered separately, so it is excluded from the unit cost.
        total = money(total - money(order.scrap_cost))
        produced = money(order.produced_quantity)
        if produced <= 0:
            planned = money(order.planned_quantity) or Decimal("1")
            return money(total / planned)
        return money(total / produced)

    def close(self, order_id: uuid.UUID, *, post: bool = True) -> ProductionOrder:
        order = self.get_document(order_id)
        if order.status in {ProductionStatus.COMPLETED.value, ProductionStatus.CANCELLED.value}:
            raise BusinessRuleError("This production order is already closed")
        if money(order.produced_quantity) <= 0 and money(order.scrap_quantity) <= 0:
            raise BusinessRuleError("Nothing was produced; record output before closing")
        # Release any reservation that was not consumed.
        inventory = self.inventory()
        for material in order.materials:
            outstanding = money(material.planned_quantity) - money(material.issued_quantity)
            if outstanding > 0:
                # The reservation may already have been released (e.g. partial issues).
                with contextlib.suppress(Exception):
                    inventory.release_reservation(
                        material.product_id, material.warehouse_id or order.warehouse_id, outstanding
                    )
        order.total_cost = money(
            Decimal(order.material_cost or 0) + Decimal(order.labour_cost or 0) + Decimal(order.overhead_cost or 0)
        )
        order.unit_cost = self._current_unit_cost(order)
        order.actual_end_date = datetime.now(UTC)
        if post:
            self.post(order)
        order.status = ProductionStatus.COMPLETED.value
        self._record_cost_sheet(order)
        self.db.flush()
        self.audit.log_action(
            AuditAction.CLOSE, order, entity_type="production_order", label=order.document_no
        )
        return order

    def _record_cost_sheet(self, order: ProductionOrder) -> ProductionCostSheet:
        sheet = ProductionCostSheet(
            company_id=self.company_id,
            production_order_id=order.id,
            cost_date=(order.actual_end_date.date() if isinstance(order.actual_end_date, datetime) else order.actual_end_date) or date.today(),
            material_cost=money(order.material_cost),
            labour_cost=money(order.labour_cost),
            machine_cost=money(
                sum((Decimal(op.machine_cost or 0) for op in order.operations), ZERO)
            ),
            overhead_cost=money(order.overhead_cost),
            scrap_cost=money(order.scrap_cost),
            total_cost=money(order.total_cost),
            produced_quantity=money(order.produced_quantity),
            unit_cost=money(order.unit_cost),
            journal_entry_id=order.journal_entry_id,
            details_json={
                "materials": [
                    {
                        "product_id": str(material.product_id),
                        "planned": str(material.planned_quantity),
                        "issued": str(material.issued_quantity),
                        "cost": str(money(material.total_cost)),
                    }
                    for material in order.materials
                ],
                "operations": [
                    {
                        "name": operation.name,
                        "minutes": str(money(operation.actual_minutes)),
                        "labour": str(money(operation.labour_cost)),
                        "machine": str(money(operation.machine_cost)),
                        "overhead": str(money(operation.overhead_cost)),
                    }
                    for operation in order.operations
                ],
            },
        )
        self.db.add(sheet)
        self.db.flush()
        return sheet

    def analyze_variance(self, order_id: uuid.UUID) -> dict[str, Any]:
        order = self.get_document(order_id)
        bom = BomService(self.db, self.company_id).get(order.bom_id) if order.bom_id else None
        standard_unit = money(bom.standard_cost) if bom else ZERO
        actual_unit = money(order.unit_cost)
        planned_material = sum((money(item.total_cost) for item in order.materials), ZERO)
        return {
            "order": order.document_no,
            "planned_quantity": str(quantity(order.planned_quantity)),
            "produced_quantity": str(quantity(order.produced_quantity)),
            "standard_unit_cost": str(standard_unit),
            "actual_unit_cost": str(actual_unit),
            "unit_variance": str(money(actual_unit - standard_unit)),
            "material_cost": str(money(order.material_cost)),
            "planned_material_cost": str(money(planned_material)),
            "labour_cost": str(money(order.labour_cost)),
            "overhead_cost": str(money(order.overhead_cost)),
            "total_cost": str(money(order.total_cost)),
            "variance_amount": str(money(Decimal(order.total_cost or 0) - standard_unit * money(order.produced_quantity))),
            "scrap_cost": str(money(order.scrap_cost)),
        }

    # ---------------------------------------------------------------- posting
    def validate_posting(self, document: ProductionOrder) -> None:
        if money(document.produced_quantity) <= 0 and money(document.scrap_quantity) <= 0:
            raise BusinessRuleError("Record production output before posting the order")

    def build_journal_lines(self, document: ProductionOrder, inventory_result: Any = None) -> list[EntryLine]:
        """Capitalise the production cost into inventory (WIP -> finished goods)."""
        total = money(
            Decimal(document.material_cost or 0)
            + Decimal(document.labour_cost or 0)
            + Decimal(document.overhead_cost or 0)
        )
        if total <= 0:
            return []
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        wip_account = self.posting.resolve_account("wip", document_type=self.document_type, fallback_code="1320")
        lines = [
            EntryLine(
                account_id=wip_account.id,
                debit=total,
                description=f"Production cost {document.document_no}",
                branch_id=document.branch_id,
                project_id=document.project_id,
            ),
        ]
        material_cost = money(document.material_cost)
        labour_cost = money(Decimal(document.labour_cost or 0) + Decimal(document.overhead_cost or 0))
        if material_cost > 0:
            lines.append(
                EntryLine(
                    account_id=inventory_account.id,
                    credit=material_cost,
                    description=f"Materials consumed {document.document_no}",
                )
            )
        if labour_cost > 0:
            labour_account = self.posting.resolve_account(
                "manufacturing_overhead", document_type=self.document_type, fallback_code="5180"
            )
            lines.append(
                EntryLine(
                    account_id=labour_account.id,
                    credit=labour_cost,
                    description=f"Labour and overhead applied {document.document_no}",
                )
            )
        # Finished goods come out of WIP at the accumulated unit cost.
        finished_value = money(money(document.produced_quantity) * money(document.unit_cost))
        if finished_value > 0:
            lines.append(
                EntryLine(
                    account_id=wip_account.id,
                    credit=finished_value,
                    description=f"Finished goods {document.document_no}",
                )
            )
            lines.append(
                EntryLine(
                    account_id=inventory_account.id,
                    debit=finished_value,
                    description=f"Finished goods {document.document_no}",
                )
            )
        scr = money(document.scrap_cost)
        if scr > 0:
            stocked = money((document.extra_data or {}).get("scrap_stocked_value"))
            expensed = money(scr - stocked)
            if stocked > 0:
                lines.append(
                    EntryLine(
                        account_id=inventory_account.id,
                        debit=stocked,
                        description=f"Recovered scrap {document.document_no}",
                    )
                )
            if expensed > 0:
                scrap_account = self.posting.resolve_account(
                    "scrap", document_type=self.document_type, fallback_code="5170"
                )
                lines.append(
                    EntryLine(
                        account_id=scrap_account.id, debit=expensed, description=f"Scrap {document.document_no}"
                    )
                )
            lines.append(
                EntryLine(account_id=wip_account.id, credit=scr, description=f"Scrap {document.document_no}")
            )
        # Balance any residual WIP against the variance account so the entry is valid.
        debits = sum((line.debit for line in lines), ZERO)
        credits = sum((line.credit for line in lines), ZERO)
        difference = money(debits - credits)
        if difference != 0:
            variance_account = self.posting.resolve_account(
                "manufacturing_variance", document_type=self.document_type, fallback_code="5160"
            )
            if difference > 0:
                lines.append(
                    EntryLine(
                        account_id=variance_account.id,
                        credit=difference,
                        description=f"Production variance {document.document_no}",
                    )
                )
            else:
                lines.append(
                    EntryLine(
                        account_id=variance_account.id,
                        debit=abs(difference),
                        description=f"Production variance {document.document_no}",
                    )
                )
        return lines

    def after_post(self, document: ProductionOrder, inventory_result: Any = None, entry: Any = None) -> None:
        document.wip_balance = ZERO
        document.posted_by_id = self.user_id
        document.posted_at = datetime.now(UTC)
        if document.project_id:
            from app.models.projects import Project

            project = self.db.get(Project, document.project_id)
            if project:
                project.actual_materials = money(
                    Decimal(project.actual_materials or 0) + money(document.material_cost)
                )
        self.db.flush()
