"""Warehouse stock documents: transfers, adjustments and physical counts.

These are the documents that move stock without a commercial counterpart.  All
of them write to the immutable stock ledger through :class:`InventoryService`
and post the matching accounting entry so inventory and the general ledger never
drift apart.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.coercion import as_uuid
from app.core.enums import DocumentStatus, MovementType
from app.core.errors import BusinessRuleError, ValidationFailure
from app.models.inventory import (
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockCount,
    StockCountLine,
    StockTransfer,
    StockTransferLine,
)
from app.services.document_service import BaseDocumentService
from app.services.inventory_service import InventoryService, StockMove
from app.services.posting_service import EntryLine, money, quantity

#: Adjustment kinds and how they affect stock.
ADJUSTMENT_DIRECTIONS: dict[str, str] = {
    "increase": "in",
    "opening": "in",
    "decrease": "out",
    "scrap": "out",
    "issue": "out",
    "return": "in",
}

#: Default expense account role per adjustment kind.
ADJUSTMENT_ACCOUNT_ROLES: dict[str, tuple[str, str]] = {
    "increase": ("inventory_gain", "5130"),
    "opening": ("opening_balance", "3110"),
    "decrease": ("inventory_shrinkage", "5130"),
    "scrap": ("scrap_expense", "5170"),
    "issue": ("inventory_issue", "5130"),
    "return": ("inventory_gain", "5130"),
}


class StockTransferService(BaseDocumentService):
    """Move stock between warehouses, zones or locations."""

    document_type = "stock_transfer"
    model = StockTransfer
    line_model = StockTransferLine
    permission_module = "inventory"
    permission_entity = "stock_transfer"
    requires_lines = True

    # ------------------------------------------------------------------ creation
    def create(self, payload: dict[str, Any]) -> StockTransfer:
        inventory = InventoryService(self.db, self.company_id)
        source_id = as_uuid(payload.get("source_warehouse_id") or payload.get("from_warehouse_id"))
        destination_id = as_uuid(payload.get("destination_warehouse_id") or payload.get("to_warehouse_id"))
        if source_id is None or destination_id is None:
            raise ValidationFailure("Both the source and the destination warehouse are required")
        if source_id == destination_id:
            raise ValidationFailure("The source and destination warehouse must be different")
        source = inventory.get_warehouse(source_id)
        destination = inventory.get_warehouse(destination_id)
        document = StockTransfer(
            company_id=self.company_id,
            document_no=payload.get("document_no") or self.next_number(branch_id=source.branch_id),
            transfer_date=payload.get("transfer_date") or payload.get("document_date") or date.today(),
            source_warehouse_id=source.id,
            destination_warehouse_id=destination.id,
            source_branch_id=source.branch_id,
            destination_branch_id=destination.branch_id,
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            requested_by_id=as_uuid(payload.get("requested_by_id")) or self.user_id,
        )
        self.db.add(document)
        self.db.flush()

        rows: list[dict[str, Any]] = []
        total_cost = Decimal("0")
        for index, raw in enumerate(payload.get("lines") or [], start=1):
            product_id = as_uuid(raw.get("product_id"))
            if product_id is None:
                raise ValidationFailure(f"Line {index}: a product is required")
            unit_id = as_uuid(raw.get("unit_id"))
            qty = quantity(raw.get("quantity", 0))
            if qty <= 0:
                raise ValidationFailure(f"Line {index}: the quantity must be greater than zero")
            base_quantity = inventory.to_base_quantity(product_id, qty, unit_id)
            unit_cost = money(
                raw.get("unit_cost")
                if raw.get("unit_cost") is not None
                else inventory.average_cost(product_id, source.id)
            )
            line_total = money(base_quantity * unit_cost)
            total_cost += line_total
            rows.append(
                {
                    "sequence_no": index,
                    "product_id": product_id,
                    "unit_id": unit_id,
                    "quantity": qty,
                    "base_quantity": base_quantity,
                    "unit_cost": unit_cost,
                    "total_cost": line_total,
                    "batch_id": as_uuid(raw.get("batch_id")),
                    "serial_numbers": raw.get("serial_numbers") or None,
                    "source_location_id": as_uuid(raw.get("source_location_id")),
                    "destination_location_id": as_uuid(raw.get("destination_location_id")),
                    "notes": raw.get("notes"),
                }
            )
        if not rows:
            raise ValidationFailure("A stock transfer requires at least one line")
        self.apply_line_rows(document, rows)
        document.total_cost = money(total_cost)
        self.db.flush()
        self.audit.log_create(document, entity_type="stock_transfer", label=document.document_no)
        return document

    # ------------------------------------------------------------------ posting
    def validate_posting(self, document: StockTransfer) -> None:
        if not document.lines:
            raise BusinessRuleError("A stock transfer requires at least one line")
        inventory = InventoryService(self.db, self.company_id)
        for line in document.lines:
            available = inventory.available_quantity(line.product_id, document.source_warehouse_id)
            if quantity(line.base_quantity) > available:
                raise BusinessRuleError(
                    f"Insufficient stock in the source warehouse: available {available}, requested {line.base_quantity}",
                    product_id=str(line.product_id),
                )

    def apply_inventory(self, document: StockTransfer) -> dict[str, Any]:
        inventory = InventoryService(self.db, self.company_id)
        results: list[Any] = []
        total_cost = Decimal("0")
        for line in document.lines:
            outbound = inventory.move(
                StockMove(
                    product_id=line.product_id,
                    warehouse_id=document.source_warehouse_id,
                    quantity=quantity(line.quantity),
                    unit_id=line.unit_id,
                    movement_type=MovementType.TRANSFER_OUT,
                    entry_date=document.transfer_date,
                    location_id=line.source_location_id,
                    batch_id=line.batch_id,
                    serial_numbers=line.serial_numbers,
                    reference_type=self.document_type,
                    reference_id=document.id,
                    reference_no=document.document_no,
                    reference_line_id=line.id,
                    notes=f"Transfer to {document.destination_warehouse_id}",
                )
            )
            line.base_quantity = quantity(outbound.ledger_entry.base_quantity)
            line.unit_cost = money(outbound.unit_cost)
            line.total_cost = money(outbound.total_cost)
            total_cost += money(outbound.total_cost)
            results.append(outbound)
            results.append(
                inventory.move(
                    StockMove(
                        product_id=line.product_id,
                        warehouse_id=document.destination_warehouse_id,
                        quantity=quantity(outbound.ledger_entry.base_quantity),
                        unit_id=None,
                        unit_cost=money(outbound.unit_cost),
                        movement_type=MovementType.TRANSFER_IN,
                        entry_date=document.transfer_date,
                        location_id=line.destination_location_id,
                        batch_id=line.batch_id,
                        reference_type=self.document_type,
                        reference_id=document.id,
                        reference_no=document.document_no,
                        reference_line_id=line.id,
                        notes=f"Transfer from {document.source_warehouse_id}",
                    )
                )
            )
        document.total_cost = money(total_cost)
        self.db.flush()
        return {"moves": results, "total_cost": document.total_cost}

    def build_journal_lines(self, document: StockTransfer, inventory_result: Any = None) -> list[EntryLine]:
        """A transfer between warehouses of one company never changes the GL."""
        return []

    def availability(self, *, warehouse_id: uuid.UUID, product_ids: list[uuid.UUID] | None = None) -> list[dict[str, Any]]:
        """Pick list used by the transfer screen."""
        inventory = InventoryService(self.db, self.company_id)
        stmt = select(StockBalance).where(
            StockBalance.company_id == self.company_id,
            StockBalance.warehouse_id == warehouse_id,
            StockBalance.quantity > 0,
        )
        if product_ids:
            stmt = stmt.where(StockBalance.product_id.in_(product_ids))
        rows = self.db.execute(stmt.limit(500)).scalars().all()
        return [
            {
                "product_id": str(row.product_id),
                "warehouse_id": str(row.warehouse_id),
                "batch_id": str(row.batch_id) if row.batch_id else None,
                "quantity": str(inventory.available_quantity(row.product_id, warehouse_id, row.batch_id)),
                "average_cost": str(row.average_cost or 0),
            }
            for row in rows
        ]


class StockAdjustmentService(BaseDocumentService):
    """Increase/decrease stock: opening balances, shrinkage, scrap and issues."""

    document_type = "stock_adjustment"
    model = StockAdjustment
    line_model = StockAdjustmentLine
    permission_module = "inventory"
    permission_entity = "stock_adjustment"
    requires_lines = True

    def create(self, payload: dict[str, Any]) -> StockAdjustment:
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = as_uuid(payload.get("warehouse_id"))
        if warehouse_id is None:
            raise ValidationFailure("A warehouse is required")
        warehouse = inventory.get_warehouse(warehouse_id)
        adjustment_type = str(payload.get("adjustment_type") or "increase")
        if adjustment_type not in ADJUSTMENT_DIRECTIONS:
            raise ValidationFailure(
                f"Unknown adjustment type '{adjustment_type}'", allowed=sorted(ADJUSTMENT_DIRECTIONS)
            )
        document = StockAdjustment(
            company_id=self.company_id,
            document_no=payload.get("document_no") or self.next_number(branch_id=warehouse.branch_id),
            adjustment_date=payload.get("adjustment_date") or payload.get("document_date") or date.today(),
            warehouse_id=warehouse.id,
            adjustment_type=adjustment_type,
            reason=payload.get("reason"),
            offset_account_id=as_uuid(payload.get("offset_account_id")),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(document)
        self.db.flush()

        default_direction = ADJUSTMENT_DIRECTIONS[adjustment_type]
        rows: list[dict[str, Any]] = []
        total_cost = Decimal("0")
        for index, raw in enumerate(payload.get("lines") or [], start=1):
            product_id = as_uuid(raw.get("product_id"))
            if product_id is None:
                raise ValidationFailure(f"Line {index}: a product is required")
            unit_id = as_uuid(raw.get("unit_id"))
            qty = quantity(raw.get("quantity", raw.get("base_quantity", 0)))
            if qty <= 0:
                raise ValidationFailure(f"Line {index}: the quantity must be greater than zero")
            base_quantity = inventory.to_base_quantity(product_id, qty, unit_id)
            direction = str(raw.get("direction") or default_direction)
            if direction not in {"in", "out"}:
                raise ValidationFailure(f"Line {index}: direction must be 'in' or 'out'")
            if raw.get("unit_cost") is not None:
                unit_cost = money(raw["unit_cost"])
            elif direction == "in":
                unit_cost = money(inventory.average_cost(product_id, warehouse.id)) or money(
                    inventory.get_product(product_id).cost_price
                )
            else:
                unit_cost = money(inventory.average_cost(product_id, warehouse.id))
            line_total = money(base_quantity * unit_cost)
            total_cost += line_total
            rows.append(
                {
                    "sequence_no": index,
                    "product_id": product_id,
                    "unit_id": unit_id,
                    "quantity": qty,
                    "base_quantity": base_quantity,
                    "unit_cost": unit_cost,
                    "total_cost": line_total,
                    "direction": direction,
                    "batch_id": as_uuid(raw.get("batch_id")),
                    "serial_numbers": raw.get("serial_numbers") or None,
                    "location_id": as_uuid(raw.get("location_id")),
                    "notes": raw.get("notes"),
                }
            )
        if not rows:
            raise ValidationFailure("A stock adjustment requires at least one line")
        self.apply_line_rows(document, rows)
        document.total_cost = money(total_cost)
        self.db.flush()
        self.audit.log_create(document, entity_type="stock_adjustment", label=document.document_no)
        return document

    def validate_posting(self, document: StockAdjustment) -> None:
        if not document.lines:
            raise BusinessRuleError("A stock adjustment requires at least one line")
        inventory = InventoryService(self.db, self.company_id)
        for line in document.lines:
            if line.direction == "out":
                available = inventory.available_quantity(line.product_id, document.warehouse_id)
                if quantity(line.base_quantity) > available:
                    raise BusinessRuleError(
                        f"Insufficient stock to decrease: available {available}, requested {line.base_quantity}",
                        product_id=str(line.product_id),
                    )

    def apply_inventory(self, document: StockAdjustment) -> dict[str, Any]:
        inventory = InventoryService(self.db, self.company_id)
        results: list[Any] = []
        total_cost = Decimal("0")
        for line in document.lines:
            inbound = line.direction == "in"
            result = inventory.move(
                StockMove(
                    product_id=line.product_id,
                    warehouse_id=document.warehouse_id,
                    quantity=quantity(line.base_quantity),
                    unit_cost=money(line.unit_cost),
                    movement_type=MovementType.ADJUSTMENT_IN if inbound else MovementType.ADJUSTMENT_OUT,
                    entry_date=document.adjustment_date,
                    location_id=line.location_id,
                    batch_id=line.batch_id,
                    serial_numbers=line.serial_numbers,
                    reference_type=self.document_type,
                    reference_id=document.id,
                    reference_no=document.document_no,
                    reference_line_id=line.id,
                    notes=document.reason,
                )
            )
            line.unit_cost = money(result.unit_cost)
            line.total_cost = money(result.total_cost)
            total_cost += money(result.total_cost) if inbound else -money(result.total_cost)
            results.append(result)
        document.total_cost = money(total_cost)
        self.db.flush()
        return {"moves": results, "total_cost": document.total_cost}

    def build_journal_lines(self, document: StockAdjustment, inventory_result: Any = None) -> list[EntryLine]:
        inventory = InventoryService(self.db, self.company_id)
        role, fallback = ADJUSTMENT_ACCOUNT_ROLES.get(document.adjustment_type, ("inventory_shrinkage", "5130"))
        offset = self.posting.resolve_account(
            role,
            document_type=self.document_type,
            explicit_account_id=document.offset_account_id,
            fallback_code=fallback,
        )
        inbound_total = Decimal("0")
        outbound_total = Decimal("0")
        for line in document.lines:
            value = money(Decimal(line.base_quantity) * money(line.unit_cost))
            if line.direction == "in":
                inbound_total += value
            else:
                outbound_total += value
        inventory_account = self.posting.resolve_account(
            "inventory",
            document_type=self.document_type,
            explicit_account_id=inventory.get_warehouse(document.warehouse_id).inventory_account_id,
            fallback_code="1310",
        )
        lines: list[EntryLine] = []
        if inbound_total > 0:
            lines.append(
                EntryLine(
                    account_id=inventory_account.id,
                    debit=money(inbound_total),
                    description=f"Stock adjustment {document.document_no}",
                )
            )
            lines.append(
                EntryLine(
                    account_id=offset.id,
                    credit=money(inbound_total),
                    description=document.reason or "Stock increase",
                )
            )
        if outbound_total > 0:
            lines.append(
                EntryLine(
                    account_id=offset.id,
                    debit=money(outbound_total),
                    description=document.reason or "Stock decrease",
                )
            )
            lines.append(
                EntryLine(
                    account_id=inventory_account.id,
                    credit=money(outbound_total),
                    description=f"Stock adjustment {document.document_no}",
                )
            )
        return lines


class StockCountService(BaseDocumentService):
    """Physical stocktake: snapshot the system quantity, record counts, post variances."""

    document_type = "stock_count"
    model = StockCount
    line_model = StockCountLine
    permission_module = "inventory"
    permission_entity = "stock_count"
    requires_lines = False

    def create(self, payload: dict[str, Any]) -> StockCount:
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = as_uuid(payload.get("warehouse_id"))
        if warehouse_id is None:
            raise ValidationFailure("A warehouse is required")
        warehouse = inventory.get_warehouse(warehouse_id)
        document = StockCount(
            company_id=self.company_id,
            document_no=payload.get("document_no") or self.next_number(branch_id=warehouse.branch_id),
            count_date=payload.get("count_date") or payload.get("document_date") or date.today(),
            warehouse_id=warehouse.id,
            zone_id=as_uuid(payload.get("zone_id")),
            status=DocumentStatus.DRAFT.value,
            count_type=str(payload.get("count_type") or "full"),
            responsible_id=as_uuid(payload.get("responsible_id")) or self.user_id,
            notes=payload.get("notes"),
        )
        self.db.add(document)
        self.db.flush()
        rows = payload.get("lines")
        if not rows:
            rows = self._snapshot_lines(inventory, warehouse.id)
        self.apply_line_rows(document, rows)
        self.db.flush()
        self.audit.log_create(document, entity_type="stock_count", label=document.document_no)
        return document

    def _snapshot_lines(self, inventory: InventoryService, warehouse_id: uuid.UUID) -> list[dict[str, Any]]:
        balances = self.db.execute(
            select(StockBalance).where(
                StockBalance.company_id == self.company_id,
                StockBalance.warehouse_id == warehouse_id,
                StockBalance.quantity != 0,
            )
        ).scalars().all()
        rows: list[dict[str, Any]] = []
        for index, balance in enumerate(balances, start=1):
            rows.append(
                {
                    "sequence_no": index,
                    "product_id": balance.product_id,
                    "batch_id": balance.batch_id,
                    "system_quantity": quantity(balance.quantity),
                    "counted_quantity": None,
                    "unit_cost": money(balance.average_cost),
                }
            )
        return rows

    def record_counts(self, document: StockCount, entries: list[dict[str, Any]]) -> StockCount:
        """Store the counted quantities coming back from the warehouse."""
        self.ensure_editable(document)
        by_id = {line.id: line for line in document.lines}
        by_product: dict[uuid.UUID, StockCountLine] = {}
        for line in document.lines:
            by_product.setdefault(line.product_id, line)
        for index, entry in enumerate(entries, start=1):
            line = None
            line_id = as_uuid(entry.get("line_id"))
            if line_id is not None:
                line = by_id.get(line_id)
            if line is None:
                product_id = as_uuid(entry.get("product_id"))
                line = by_product.get(product_id) if product_id else None
            if line is None:
                raise ValidationFailure(f"Entry {index} does not match a counted line")
            if entry.get("counted_quantity") is None:
                raise ValidationFailure(f"Entry {index}: counted quantity is required")
            line.counted_quantity = quantity(entry["counted_quantity"])
            line.is_counted = True
            if entry.get("notes"):
                line.notes = entry["notes"]
            line.variance_quantity = quantity(Decimal(line.counted_quantity) - Decimal(line.system_quantity))
            line.variance_value = money(Decimal(line.variance_quantity) * money(line.unit_cost))
        self.db.flush()
        return document

    def validate_posting(self, document: StockCount) -> None:
        if not document.lines:
            raise BusinessRuleError("The stock count has no lines")
        uncounted = [line for line in document.lines if not line.is_counted]
        if uncounted:
            raise BusinessRuleError(
                "Every line must be counted before posting the stocktake", pending=len(uncounted)
            )

    def apply_inventory(self, document: StockCount) -> dict[str, Any]:
        """The count itself does not move stock: the variance adjustment does."""
        return {
            "variances": [
                {
                    "product_id": str(line.product_id),
                    "variance_quantity": str(line.variance_quantity),
                    "variance_value": str(line.variance_value),
                }
                for line in document.lines
                if Decimal(line.variance_quantity or 0) != 0
            ]
        }

    def after_post(self, document: StockCount, inventory_result: Any = None, entry: Any = None) -> None:
        """Create and post the variance adjustment for every counted difference."""
        variances = [
            line for line in document.lines if Decimal(line.variance_quantity or 0) != 0
        ]
        if not variances:
            document.adjustment_id = None
            return
        adjustment_payload = {
            "warehouse_id": document.warehouse_id,
            "adjustment_date": document.count_date,
            "adjustment_type": "increase",
            "reason": f"Stocktake variance {document.document_no}",
            "notes": document.notes,
            "lines": [
                {
                    "product_id": line.product_id,
                    "unit_id": line.unit_id,
                    "quantity": abs(Decimal(line.variance_quantity)),
                    "direction": "in" if Decimal(line.variance_quantity) > 0 else "out",
                    "unit_cost": money(line.unit_cost),
                    "batch_id": line.batch_id,
                    "location_id": line.location_id,
                    "notes": line.notes,
                }
                for line in variances
            ],
        }
        adjustment_service = StockAdjustmentService(
            self.db, self.company_id, user_id=self.user_id, audit_context=self.audit.context
        )
        adjustment = adjustment_service.create(adjustment_payload)
        adjustment.status = DocumentStatus.APPROVED.value
        self.db.flush()
        adjustment_service.post(adjustment)
        document.adjustment_id = adjustment.id
        document.completed_at = document.completed_at or _now()
        self.db.flush()

    def post(self, document: StockCount, *, allow_draft: bool = False) -> Any:  # type: ignore[override]
        """Stocktakes are posted straight from draft: the count is the approval."""
        return super().post(document, allow_draft=True)


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


__all__ = [
    "ADJUSTMENT_ACCOUNT_ROLES",
    "ADJUSTMENT_DIRECTIONS",
    "StockAdjustmentService",
    "StockCountService",
    "StockTransferService",
]
