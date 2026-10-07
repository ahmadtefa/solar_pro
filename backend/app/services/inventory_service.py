"""Inventory engine.

Every quantity change flows through :meth:`InventoryService.move`, which:

1. resolves the unit conversion factor and computes the base quantity,
2. validates availability (unless negative stock is explicitly allowed),
3. computes the cost using the product's valuation method (weighted average,
   FIFO layers or standard cost),
4. appends an immutable ``stock_ledger_entries`` row carrying the running
   balance, and
5. updates the ``stock_balances`` aggregate in the same transaction.

Because ledger and balance are written together inside the caller's
transaction, an invoice that fails later leaves inventory untouched.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    INBOUND_MOVEMENTS,
    OUTBOUND_MOVEMENTS,
    MovementType,
    PartyType,
    ProductType,
    ValuationMethod,
)
from app.core.errors import BusinessRuleError, NotFoundError
from app.models.inventory import (
    Batch,
    InventoryValuationLayer,
    SerialNumber,
    StockBalance,
    StockLedgerEntry,
)
from app.models.masterdata import Product, ProductUnit, Warehouse
from app.models.platform import UnitOfMeasure

FOUR_PLACES = Decimal("0.0001")
TWO_PLACES = Decimal("0.01")


def qty(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def money(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class StockMove:
    """Requested stock movement."""

    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: Decimal
    movement_type: MovementType | str
    unit_id: uuid.UUID | None = None
    unit_cost: Decimal | None = None
    entry_date: date | None = None
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    expiry_date: date | None = None
    location_id: uuid.UUID | None = None
    serial_numbers: list[str] | None = None
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    reference_no: str | None = None
    reference_line_id: uuid.UUID | None = None
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    notes: str | None = None
    allow_negative: bool | None = None
    skip_serial_validation: bool = False
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StockMoveResult:
    ledger_entry: StockLedgerEntry
    unit_cost: Decimal
    total_cost: Decimal
    balance_quantity: Decimal
    balance_value: Decimal
    average_cost: Decimal


class InventoryService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id

    # ------------------------------------------------------------- utilities
    def get_product(self, product_id: uuid.UUID) -> Product:
        product = self.db.execute(
            select(Product).where(Product.company_id == self.company_id, Product.id == product_id)
        ).scalars().first()
        if product is None:
            raise NotFoundError("Product not found", product_id=str(product_id))
        return product

    def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = self.db.execute(
            select(Warehouse).where(Warehouse.company_id == self.company_id, Warehouse.id == warehouse_id)
        ).scalars().first()
        if warehouse is None:
            raise NotFoundError("Warehouse not found", warehouse_id=str(warehouse_id))
        return warehouse

    def unit_factor(self, product_id: uuid.UUID, unit_id: uuid.UUID | None) -> Decimal:
        """Convert ``unit_id`` to the product base unit."""
        if unit_id is None:
            return Decimal("1")
        product_unit = self.db.execute(
            select(ProductUnit).where(
                ProductUnit.company_id == self.company_id,
                ProductUnit.product_id == product_id,
                ProductUnit.unit_id == unit_id,
            )
        ).scalars().first()
        if product_unit is not None:
            return Decimal(product_unit.conversion_factor or 1)
        return Decimal("1")

    def to_base_quantity(self, product_id: uuid.UUID, quantity: Decimal, unit_id: uuid.UUID | None) -> Decimal:
        return qty(Decimal(quantity or 0) * self.unit_factor(product_id, unit_id))

    # -------------------------------------------------------------- balances
    def _balance_row(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, batch_id: uuid.UUID | None, *, lock: bool = True
    ) -> StockBalance | None:
        stmt = select(StockBalance).where(
            StockBalance.company_id == self.company_id,
            StockBalance.product_id == product_id,
            StockBalance.warehouse_id == warehouse_id,
            StockBalance.batch_id.is_(None) if batch_id is None else StockBalance.batch_id == batch_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalars().first()

    def get_or_create_balance(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, batch_id: uuid.UUID | None = None
    ) -> StockBalance:
        balance = self._balance_row(product_id, warehouse_id, batch_id)
        if balance is None:
            balance = StockBalance(
                company_id=self.company_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                batch_id=batch_id,
                quantity=Decimal("0"),
                total_value=Decimal("0"),
                average_cost=Decimal("0"),
            )
            self.db.add(balance)
            self.db.flush()
        return balance

    def stock_on_hand(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None, batch_id: uuid.UUID | None = None
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
            StockBalance.company_id == self.company_id,
            StockBalance.product_id == product_id,
        )
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        if batch_id:
            stmt = stmt.where(StockBalance.batch_id == batch_id)
        return qty(self.db.execute(stmt).scalar_one())

    def available_quantity(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None, batch_id: uuid.UUID | None = None
    ) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(StockBalance.quantity), 0),
            func.coalesce(func.sum(StockBalance.reserved_quantity), 0),
        ).where(StockBalance.company_id == self.company_id, StockBalance.product_id == product_id)
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        if batch_id:
            stmt = stmt.where(StockBalance.batch_id == batch_id)
        on_hand, reserved = self.db.execute(stmt).one()
        return qty(Decimal(on_hand or 0) - Decimal(reserved or 0))

    def stock_value(self, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None) -> Decimal:
        stmt = select(func.coalesce(func.sum(StockBalance.total_value), 0)).where(
            StockBalance.company_id == self.company_id, StockBalance.product_id == product_id
        )
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        return money(self.db.execute(stmt).scalar_one())

    def average_cost(self, product_id: uuid.UUID, warehouse_id: uuid.UUID | None = None) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(StockBalance.quantity), 0), func.coalesce(func.sum(StockBalance.total_value), 0)
        ).where(StockBalance.company_id == self.company_id, StockBalance.product_id == product_id)
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        on_hand, value = self.db.execute(stmt).one()
        on_hand = Decimal(on_hand or 0)
        if on_hand <= 0:
            return Decimal("0")
        return (Decimal(value or 0) / on_hand).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def low_stock_items(self, warehouse_id: uuid.UUID | None = None, limit: int = 100) -> list[dict[str, Any]]:
        stmt = (
            select(StockBalance, Product)
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                StockBalance.company_id == self.company_id,
                Product.is_active.is_(True),
                Product.track_inventory.is_(True),
                Product.reorder_level > 0,
                StockBalance.quantity <= Product.reorder_level,
            )
        )
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        rows = self.db.execute(stmt.limit(limit)).all()
        return [
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "warehouse_id": balance.warehouse_id,
                "quantity": balance.quantity,
                "reorder_level": product.reorder_level,
                "shortage": qty(Decimal(product.reorder_level or 0) - Decimal(balance.quantity or 0)),
                "average_cost": balance.average_cost,
                "value": balance.total_value,
            }
            for balance, product in rows
        ]

    # ------------------------------------------------------------ reservations
    def reserve(self, product_id: uuid.UUID, warehouse_id: uuid.UUID, quantity: Decimal) -> StockBalance:
        balance = self.get_or_create_balance(product_id, warehouse_id)
        requested = qty(quantity)
        if requested > qty(Decimal(balance.quantity or 0) - Decimal(balance.reserved_quantity or 0)):
            raise BusinessRuleError("Not enough available stock to reserve", product_id=str(product_id))
        balance.reserved_quantity = qty(Decimal(balance.reserved_quantity or 0) + requested)
        self.db.flush()
        return balance

    def release_reservation(
        self, product_id: uuid.UUID, warehouse_id: uuid.UUID, quantity: Decimal
    ) -> StockBalance:
        balance = self.get_or_create_balance(product_id, warehouse_id)
        balance.reserved_quantity = qty(
            max(Decimal("0"), Decimal(balance.reserved_quantity or 0) - qty(quantity))
        )
        self.db.flush()
        return balance

    # ------------------------------------------------------------------ moves
    def move(self, request: StockMove) -> StockMoveResult:
        movement_type = MovementType(str(request.movement_type))
        is_inbound = movement_type in INBOUND_MOVEMENTS
        if movement_type not in INBOUND_MOVEMENTS and movement_type not in OUTBOUND_MOVEMENTS:
            raise BusinessRuleError(f"Unsupported movement type {movement_type}")

        product = self.get_product(request.product_id)
        warehouse = self.get_warehouse(request.warehouse_id)
        entry_date = request.entry_date or date.today()

        base_quantity = self.to_base_quantity(product.id, request.quantity, request.unit_id)
        if base_quantity <= 0:
            raise BusinessRuleError("Stock movement quantity must be greater than zero")

        if product.product_type == ProductType.SERVICE.value and product.track_inventory:
            # Service items are normally non stock tracked; if forced, still allow but note it.
            pass

        batch = self._resolve_batch(request, product)

        balance = self.get_or_create_balance(product.id, warehouse.id, batch.id if batch else request.batch_id)
        current_qty = Decimal(balance.quantity or 0)
        current_value = Decimal(balance.total_value or 0)

        if not is_inbound:
            allow_negative = (
                request.allow_negative
                if request.allow_negative is not None
                else (product.allow_negative_stock or warehouse.allows_negative_stock)
            )
            if not allow_negative and base_quantity > current_qty:
                raise BusinessRuleError(
                    f"Insufficient stock for {product.sku or product.name}: available {current_qty}, requested {base_quantity}",
                    product_id=str(product.id),
                    warehouse_id=str(warehouse.id),
                    available=str(current_qty),
                    requested=str(base_quantity),
                )

        if is_inbound:
            unit_cost = self._inbound_unit_cost(product, request, base_quantity, current_qty, current_value)
            new_qty = qty(current_qty + base_quantity)
            new_value = money(current_value + money(base_quantity * unit_cost))
            if product.valuation_method == ValuationMethod.FIFO.value:
                self._create_fifo_layer(product, warehouse, batch, entry_date, base_quantity, unit_cost)
        else:
            unit_cost = self._outbound_unit_cost(product, request, base_quantity, current_qty, current_value)
            new_qty = qty(current_qty - base_quantity)
            new_value = money(max(Decimal("0"), current_value - money(base_quantity * unit_cost)))
            if product.valuation_method == ValuationMethod.FIFO.value:
                unit_cost = self._consume_fifo_layers(product, warehouse, batch, base_quantity)
                new_value = money(max(Decimal("0"), current_value - money(base_quantity * unit_cost)))

        average_cost = (new_value / new_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if new_qty > 0 else Decimal("0")
        total_cost = money(base_quantity * unit_cost)

        ledger_entry = StockLedgerEntry(
            company_id=self.company_id,
            entry_date=entry_date,
            posted_at=datetime.now(UTC),
            movement_type=movement_type.value,
            direction="in" if is_inbound else "out",
            product_id=product.id,
            warehouse_id=warehouse.id,
            location_id=request.location_id,
            unit_id=request.unit_id or product.unit_id,
            quantity=qty(request.quantity),
            base_quantity=base_quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            batch_id=batch.id if batch else request.batch_id,
            balance_quantity=new_qty,
            balance_value=new_value,
            average_cost=average_cost,
            reference_type=request.reference_type,
            reference_id=request.reference_id,
            reference_no=request.reference_no,
            reference_line_id=request.reference_line_id,
            party_type=request.party_type,
            party_id=request.party_id,
            notes=request.notes,
            extra_data=dict(request.extra_data or {}),
        )
        self.db.add(ledger_entry)
        self.db.flush()

        balance.quantity = new_qty
        balance.total_value = new_value
        balance.average_cost = average_cost
        balance.last_movement_at = datetime.now(UTC)
        if product.reorder_level:
            balance.reorder_alert = new_qty <= Decimal(product.reorder_level or 0)
        self.db.flush()

        if product.track_serials and request.serial_numbers:
            self._handle_serials(product, warehouse, request, batch, ledger_entry, is_inbound)

        return StockMoveResult(
            ledger_entry=ledger_entry,
            unit_cost=unit_cost,
            total_cost=total_cost,
            balance_quantity=new_qty,
            balance_value=new_value,
            average_cost=average_cost,
        )

    def move_many(self, requests: Iterable[StockMove]) -> list[StockMoveResult]:
        return [self.move(request) for request in requests]

    # ------------------------------------------------------------------ cost
    def _inbound_unit_cost(
        self,
        product: Product,
        request: StockMove,
        base_quantity: Decimal,
        current_qty: Decimal,
        current_value: Decimal,
    ) -> Decimal:
        if request.unit_cost is not None:
            return Decimal(request.unit_cost).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if product.valuation_method == ValuationMethod.STANDARD.value and product.standard_cost:
            return Decimal(product.standard_cost)
        if current_qty > 0 and current_value > 0:
            return (current_value / current_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return Decimal(product.cost_price or product.purchase_price or 0)

    def _outbound_unit_cost(
        self,
        product: Product,
        request: StockMove,
        base_quantity: Decimal,
        current_qty: Decimal,
        current_value: Decimal,
    ) -> Decimal:
        if request.unit_cost is not None:
            return Decimal(request.unit_cost).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if product.valuation_method == ValuationMethod.STANDARD.value and product.standard_cost:
            return Decimal(product.standard_cost)
        if current_qty > 0 and current_value > 0:
            return (current_value / current_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return Decimal(product.cost_price or 0)

    # ------------------------------------------------------------- fifo layers
    def _create_fifo_layer(
        self,
        product: Product,
        warehouse: Warehouse,
        batch: Batch | None,
        layer_date: date,
        base_quantity: Decimal,
        unit_cost: Decimal,
    ) -> InventoryValuationLayer:
        layer = InventoryValuationLayer(
            company_id=self.company_id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            batch_id=batch.id if batch else None,
            layer_date=layer_date,
            original_quantity=base_quantity,
            remaining_quantity=base_quantity,
            unit_cost=unit_cost,
        )
        self.db.add(layer)
        self.db.flush()
        return layer

    def _consume_fifo_layers(
        self, product: Product, warehouse: Warehouse, batch: Batch | None, base_quantity: Decimal
    ) -> Decimal:
        stmt = (
            select(InventoryValuationLayer)
            .where(
                InventoryValuationLayer.company_id == self.company_id,
                InventoryValuationLayer.product_id == product.id,
                InventoryValuationLayer.warehouse_id == warehouse.id,
                InventoryValuationLayer.remaining_quantity > 0,
                InventoryValuationLayer.batch_id.is_(None) if batch is None else InventoryValuationLayer.batch_id == batch.id,
            )
            .order_by(InventoryValuationLayer.layer_date.asc(), InventoryValuationLayer.created_at.asc())
            .with_for_update()
        )
        layers = list(self.db.execute(stmt).scalars().all())
        remaining = base_quantity
        total_cost = Decimal("0")
        for layer in layers:
            if remaining <= 0:
                break
            take = min(Decimal(layer.remaining_quantity or 0), remaining)
            layer.remaining_quantity = qty(Decimal(layer.remaining_quantity or 0) - take)
            layer.is_exhausted = layer.remaining_quantity <= 0
            total_cost += take * Decimal(layer.unit_cost or 0)
            remaining -= take
        if remaining > 0:
            # Fall back to the last known unit cost for the uncovered quantity.
            fallback = Decimal(layers[-1].unit_cost) if layers else Decimal(product.cost_price or 0)
            total_cost += remaining * fallback
        self.db.flush()
        return (total_cost / base_quantity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------ batch
    def _resolve_batch(self, request: StockMove, product: Product) -> Batch | None:
        if request.batch_id:
            batch = self.db.execute(
                select(Batch).where(Batch.company_id == self.company_id, Batch.id == request.batch_id)
            ).scalars().first()
            if batch is None:
                raise NotFoundError("Batch not found", batch_id=str(request.batch_id))
            return batch
        if request.batch_number:
            batch = self.db.execute(
                select(Batch).where(
                    Batch.company_id == self.company_id,
                    Batch.product_id == product.id,
                    Batch.batch_number == request.batch_number,
                )
            ).scalars().first()
            if batch is None:
                batch = Batch(
                    company_id=self.company_id,
                    product_id=product.id,
                    batch_number=request.batch_number,
                    expiry_date=request.expiry_date,
                )
                self.db.add(batch)
                self.db.flush()
            return batch
        if product.track_batches and MovementType(str(request.movement_type)) in INBOUND_MOVEMENTS:
            raise BusinessRuleError(f"Product {product.sku} requires a batch number for inbound movements")
        return None

    def _handle_serials(
        self,
        product: Product,
        warehouse: Warehouse,
        request: StockMove,
        batch: Batch | None,
        ledger_entry: StockLedgerEntry,
        is_inbound: bool,
    ) -> None:
        serials = request.serial_numbers or []
        if request.skip_serial_validation:
            return
        for serial in serials:
            existing = self.db.execute(
                select(SerialNumber).where(
                    SerialNumber.company_id == self.company_id,
                    SerialNumber.product_id == product.id,
                    SerialNumber.serial_number == serial,
                )
            ).scalars().first()
            if is_inbound:
                if existing is None:
                    self.db.add(
                        SerialNumber(
                            company_id=self.company_id,
                            product_id=product.id,
                            serial_number=serial,
                            batch_id=batch.id if batch else None,
                            warehouse_id=warehouse.id,
                            location_id=request.location_id,
                            status="available",
                            reference_type=request.reference_type,
                            reference_id=request.reference_id,
                        )
                    )
                else:
                    existing.status = "available"
                    existing.warehouse_id = warehouse.id
            else:
                if existing is None:
                    raise BusinessRuleError(f"Serial number {serial} is not registered for this product")
                if existing.status not in {"available", "reserved"}:
                    raise BusinessRuleError(f"Serial number {serial} is not available (status: {existing.status})")
                existing.status = "sold" if request.reference_type in {"sales_invoice", "delivery_note", "pos_sale"} else "issued"
                existing.reference_type = request.reference_type
                existing.reference_id = request.reference_id
                existing.warehouse_id = None
        self.db.flush()

    # --------------------------------------------------------------- helpers
    def validate_availability(self, product_id: uuid.UUID, warehouse_id: uuid.UUID, quantity: Decimal) -> None:
        product = self.get_product(product_id)
        if product.allow_negative_stock or self.get_warehouse(warehouse_id).allows_negative_stock:
            return
        available = self.available_quantity(product_id, warehouse_id)
        if qty(quantity) > available:
            raise BusinessRuleError(
                "Insufficient available stock",
                product_id=str(product_id),
                available=str(available),
                requested=str(quantity),
            )

    def require_warehouse(self, warehouse_id: uuid.UUID | None) -> uuid.UUID:
        if warehouse_id:
            return warehouse_id
        default = self.db.execute(
            select(Warehouse).where(Warehouse.company_id == self.company_id, Warehouse.is_active.is_(True)).limit(1)
        ).scalars().first()
        if default is None:
            raise BusinessRuleError("No active warehouse is configured for this company")
        return default.id

    def unit_label(self, unit_id: uuid.UUID | None) -> str | None:
        if not unit_id:
            return None
        unit = self.db.execute(
            select(UnitOfMeasure).where(UnitOfMeasure.company_id == self.company_id, UnitOfMeasure.id == unit_id)
        ).scalars().first()
        return unit.symbol or unit.name if unit else None

    def reconcile_balances(self, product_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Audit helper: compares balance aggregates with the ledger."""
        stmt = select(StockBalance).where(StockBalance.company_id == self.company_id)
        if product_id:
            stmt = stmt.where(StockBalance.product_id == product_id)
        discrepancies: list[dict[str, Any]] = []
        for balance in self.db.execute(stmt).scalars().all():
            ledger_stmt = select(
                func.coalesce(func.sum(StockLedgerEntry.base_quantity), 0),
            ).where(
                StockLedgerEntry.company_id == self.company_id,
                StockLedgerEntry.product_id == balance.product_id,
                StockLedgerEntry.warehouse_id == balance.warehouse_id,
                StockLedgerEntry.batch_id.is_(None) if balance.batch_id is None else StockLedgerEntry.batch_id == balance.batch_id,
            )
            inbound = self.db.execute(
                ledger_stmt.where(StockLedgerEntry.direction == "in")
            ).scalar_one()
            outbound = self.db.execute(
                select(func.coalesce(func.sum(StockLedgerEntry.base_quantity), 0)).where(
                    StockLedgerEntry.company_id == self.company_id,
                    StockLedgerEntry.product_id == balance.product_id,
                    StockLedgerEntry.warehouse_id == balance.warehouse_id,
                    StockLedgerEntry.direction == "out",
                    StockLedgerEntry.batch_id.is_(None) if balance.batch_id is None else StockLedgerEntry.batch_id == balance.batch_id,
                )
            ).scalar_one()
            computed = qty(Decimal(inbound or 0) - Decimal(outbound or 0))
            if computed != qty(balance.quantity):
                discrepancies.append(
                    {
                        "product_id": balance.product_id,
                        "warehouse_id": balance.warehouse_id,
                        "balance_quantity": balance.quantity,
                        "ledger_quantity": computed,
                    }
                )
        return discrepancies


def reference_chain(request: StockMove) -> dict[str, Any]:
    """Small helper used by services to build a consistent reference payload."""
    return {
        "reference_type": request.reference_type,
        "reference_id": request.reference_id,
        "reference_no": request.reference_no,
        "party_type": request.party_type or PartyType.OTHER.value,
        "party_id": request.party_id,
    }


def movements_for_document(document_type: str) -> Sequence[str]:
    return {
        "sales_invoice": [MovementType.ISSUE.value],
        "delivery_note": [MovementType.ISSUE.value],
        "goods_receipt": [MovementType.RECEIPT.value],
        "purchase_invoice": [MovementType.RECEIPT.value],
        "credit_note": [MovementType.SALES_RETURN_IN.value],
        "debit_note": [MovementType.PURCHASE_RETURN_OUT.value],
        "stock_transfer": [MovementType.TRANSFER_OUT.value, MovementType.TRANSFER_IN.value],
        "stock_adjustment": [MovementType.ADJUSTMENT_IN.value, MovementType.ADJUSTMENT_OUT.value],
        "production_order": [MovementType.PRODUCTION_IN.value, MovementType.PRODUCTION_OUT.value],
    }.get(document_type, [])
