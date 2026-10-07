"""Sales module services.

Implements the full chain: quotation -> sales order -> delivery -> invoice ->
payment, plus credit notes (returns), commissions and POS (shift based retail).

Design decisions
----------------
* Stock is issued by the **delivery note** (goods physically leave) and by a
  direct invoice when it is not linked to a delivery.  This avoids double cost
  of goods sold while keeping partial delivery / partial invoicing possible.
* Every posting goes through :class:`PostingService`, so accounts are resolved
  from posting rules with chart defaults, never hardcoded.
* Credit limits are enforced at order confirmation and invoice creation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.coercion import as_uuid
from app.core.enums import (
    AuditAction,
    DocumentStatus,
    MovementType,
    PaymentMethod,
    PaymentStatus,
    ProductType,
    ShiftStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.masterdata import Customer, Product
from app.models.platform import Company, PaymentTerm
from app.models.sales import (
    CreditNote,
    CreditNoteLine,
    DeliveryNote,
    DeliveryNoteLine,
    PosCashMovement,
    PosPayment,
    PosShift,
    PosTerminal,
    Quotation,
    QuotationLine,
    SalesCommission,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
)
from app.models.treasury import CashAccount
from app.services.document_service import BaseDocumentService
from app.services.inventory_service import InventoryService, StockMove
from app.services.posting_service import EntryLine, money, quantity


def _products_map(db: Session, company_id: uuid.UUID, lines: Sequence[dict[str, Any]]) -> dict[uuid.UUID, Product]:
    ids = {uuid.UUID(str(line["product_id"])) for line in lines if line.get("product_id")}
    if not ids:
        return {}
    rows = db.execute(
        select(Product).where(Product.company_id == company_id, Product.id.in_(list(ids)))
    ).scalars().all()
    return {product.id: product for product in rows}


class _SalesDocumentService(BaseDocumentService):
    permission_module = "sales"

    def company(self) -> Company:
        company = self.db.get(Company, self.company_id)
        if company is None:
            raise NotFoundError("Company not found")
        return company

    def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = self.db.execute(
            select(Customer).where(Customer.company_id == self.company_id, Customer.id == customer_id)
        ).scalars().first()
        if customer is None:
            raise NotFoundError("Customer not found", customer_id=str(customer_id))
        return customer

    def payment_term_days(self, payment_term_id: uuid.UUID | None) -> int:
        if not payment_term_id:
            return 0
        term = self.db.execute(
            select(PaymentTerm).where(
                PaymentTerm.company_id == self.company_id, PaymentTerm.id == payment_term_id
            )
        ).scalars().first()
        return int(term.days) if term else 0

    def outstanding_receivable(self, customer_id: uuid.UUID) -> Decimal:
        value = self.db.execute(
            select(func.coalesce(func.sum(SalesInvoice.balance_amount), 0)).where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.customer_id == customer_id,
                SalesInvoice.status == DocumentStatus.POSTED.value,
                SalesInvoice.deleted_at.is_(None),
            )
        ).scalar_one()
        return money(value)

    def assert_credit_limit(self, customer: Customer, new_amount: Decimal) -> None:
        limit = money(customer.credit_limit)
        if limit <= 0:
            return
        if customer.is_credit_hold:
            raise BusinessRuleError(
                f"Customer {customer.name} is on credit hold",
                reason=customer.credit_hold_reason or "credit hold",
            )
        outstanding = self.outstanding_receivable(customer.id)
        if outstanding + money(new_amount) > limit:
            raise BusinessRuleError(
                f"Credit limit exceeded for {customer.name}",
                credit_limit=str(limit),
                outstanding=str(outstanding),
                requested=str(money(new_amount)),
            )

    def default_tax_for(self, product: Product | None):
        return self.tax_engine.tax_for_product(product, purchase=False)


# --------------------------------------------------------------------------- #
# Quotation
# --------------------------------------------------------------------------- #
class QuotationService(_SalesDocumentService):
    document_type = "quotation"
    model = Quotation
    line_model = QuotationLine
    permission_entity = "quotation"
    prices_include_tax = False

    def create(self, payload: dict[str, Any]) -> Quotation:
        customer = self.get_customer(uuid.UUID(str(payload["customer_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products)

        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        quotation = Quotation(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            customer_id=customer.id,
            salesperson_id=as_uuid(payload.get("salesperson_id")) or self.user_id,
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            status=DocumentStatus.DRAFT.value,
            valid_until=payload.get("valid_until"),
            notes=payload.get("notes"),
            terms_and_conditions=payload.get("terms_and_conditions"),
            reference=payload.get("reference"),
            created_by_id=self.user_id,
        )
        self.db.add(quotation)
        self.db.flush()
        self.apply_line_rows(quotation, rows)
        self.apply_totals(
            quotation,
            totals,
            discount_amount=_to_decimal(payload.get("discount_amount")),
            other_charges=_to_decimal(payload.get("other_charges")),
            shipping_amount=_to_decimal(payload.get("shipping_amount")),
            exchange_rate=exchange_rate,
        )
        self.audit.log_create(quotation, entity_type="quotation", label=quotation.document_no)
        return quotation

    def convert_to_order(self, quotation_id: uuid.UUID) -> SalesOrder:
        quotation = self.get_document(quotation_id)
        if quotation.status not in {DocumentStatus.DRAFT.value, DocumentStatus.APPROVED.value, DocumentStatus.SUBMITTED.value}:
            raise BusinessRuleError("Only open quotations can be converted to a sales order")
        if quotation.converted_order_id:
            raise BusinessRuleError("This quotation was already converted")
        payload = {
            "customer_id": quotation.customer_id,
            "quotation_id": quotation.id,
            "salesperson_id": quotation.salesperson_id,
            "branch_id": quotation.branch_id,
            "warehouse_id": quotation.warehouse_id,
            "currency_code": quotation.currency_code,
            "document_date": date.today(),
            "discount_amount": quotation.discount_amount,
            "other_charges": quotation.other_charges,
            "shipping_amount": quotation.shipping_amount,
            "notes": quotation.notes,
            "lines": [
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "unit_id": line.unit_id,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "tax_id": line.tax_id,
                    "warehouse_id": line.warehouse_id,
                }
                for line in quotation.lines
            ],
        }
        order_service = SalesOrderService(self.db, self.company_id, user_id=self.user_id)
        order = order_service.create(payload)
        quotation.converted_order_id = order.id
        quotation.status = DocumentStatus.CLOSED.value
        self.db.flush()
        return order


# --------------------------------------------------------------------------- #
# Sales order
# --------------------------------------------------------------------------- #
class SalesOrderService(_SalesDocumentService):
    document_type = "sales_order"
    model = SalesOrder
    line_model = SalesOrderLine
    permission_entity = "sales_order"

    def create(self, payload: dict[str, Any]) -> SalesOrder:
        customer = self.get_customer(uuid.UUID(str(payload["customer_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products)
        for row in rows:
            row["ordered_quantity"] = row["quantity"]
            row["remaining_quantity"] = row["quantity"]

        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        payment_term_id = as_uuid(payload.get("payment_term_id")) or customer.payment_term_id
        term_days = self.payment_term_days(payment_term_id) or int(customer.credit_days or 0)

        order = SalesOrder(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            customer_id=customer.id,
            quotation_id=as_uuid(payload.get("quotation_id")),
            salesperson_id=as_uuid(payload.get("salesperson_id")) or self.user_id,
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            project_id=as_uuid(payload.get("project_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            payment_term_id=payment_term_id,
            due_date=document_date + timedelta(days=term_days) if term_days else None,
            delivery_date=payload.get("delivery_date"),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            terms_and_conditions=payload.get("terms_and_conditions"),
            reference=payload.get("reference"),
            created_by_id=self.user_id,
        )
        self.db.add(order)
        self.db.flush()
        self.apply_line_rows(order, rows)
        self.apply_totals(
            order,
            totals,
            discount_amount=_to_decimal(payload.get("discount_amount")),
            other_charges=_to_decimal(payload.get("other_charges")),
            shipping_amount=_to_decimal(payload.get("shipping_amount")),
            exchange_rate=exchange_rate,
        )
        self.audit.log_create(order, entity_type="sales_order", label=order.document_no)
        return order

    def confirm(self, order_id: uuid.UUID, *, allow_credit_override: bool = False) -> SalesOrder:
        order = self.get_document(order_id)
        if order.status != DocumentStatus.DRAFT.value:
            raise BusinessRuleError("Only draft orders can be confirmed")
        customer = self.get_customer(order.customer_id)
        if not allow_credit_override:
            try:
                self.assert_credit_limit(customer, order.total_amount)
                order.credit_hold = False
                order.credit_check_notes = None
            except BusinessRuleError as exc:
                order.credit_hold = True
                order.credit_check_notes = exc.message
                self.db.flush()
                raise
        self.transition(order, DocumentStatus.APPROVED.value, action=AuditAction.APPROVE)
        return order

    # --------------------------------------------------------- fulfilment
    def create_delivery(self, order_id: uuid.UUID, payload: dict[str, Any]) -> DeliveryNote:
        order = self.get_document(order_id)
        if order.status not in {
            DocumentStatus.APPROVED.value,
            DocumentStatus.PARTIALLY_FULFILLED.value,
            DocumentStatus.DRAFT.value,
        }:
            raise BusinessRuleError("Goods can only be delivered for an approved order")
        requested = {uuid.UUID(str(line["order_line_id"])): line for line in payload.get("lines", []) if line.get("order_line_id")}
        lines_payload: list[dict[str, Any]] = []
        for line in order.lines:
            requested_line = requested.get(line.id)
            if requested_line is None and payload.get("lines"):
                continue
            deliver_qty = quantity(
                requested_line.get("quantity", line.remaining_quantity) if requested_line else line.remaining_quantity
            )
            if deliver_qty <= 0:
                continue
            if deliver_qty > quantity(line.remaining_quantity):
                raise BusinessRuleError(
                    "Delivery quantity exceeds the outstanding order quantity",
                    line=str(line.id),
                    remaining=str(line.remaining_quantity),
                )
            lines_payload.append(
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "unit_id": line.unit_id,
                    "quantity": deliver_qty,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "tax_id": line.tax_id,
                    "warehouse_id": line.warehouse_id or order.warehouse_id,
                    "batch_id": (requested_line or {}).get("batch_id"),
                    "serial_numbers": (requested_line or {}).get("serial_numbers"),
                    "sales_order_line_id": line.id,
                }
            )
        if not lines_payload:
            raise BusinessRuleError("There is nothing left to deliver on this order")

        service = DeliveryNoteService(self.db, self.company_id, user_id=self.user_id)
        delivery = service.create(
            {
                "customer_id": order.customer_id,
                "sales_order_id": order.id,
                "branch_id": order.branch_id,
                "warehouse_id": order.warehouse_id,
                "currency_code": order.currency_code,
                "document_date": payload.get("document_date") or date.today(),
                "delivery_address": payload.get("delivery_address"),
                "driver_name": payload.get("driver_name"),
                "vehicle_number": payload.get("vehicle_number"),
                "notes": payload.get("notes"),
                "lines": lines_payload,
            }
        )
        return delivery

    def create_invoice(self, order_id: uuid.UUID, payload: dict[str, Any]) -> SalesInvoice:
        order = self.get_document(order_id)
        if order.status not in {
            DocumentStatus.APPROVED.value,
            DocumentStatus.PARTIALLY_FULFILLED.value,
            DocumentStatus.FULFILLED.value,
            DocumentStatus.POSTED.value,
        }:
            raise BusinessRuleError("An invoice can only be issued for an approved order")
        requested = {uuid.UUID(str(line["order_line_id"])): line for line in payload.get("lines", []) if line.get("order_line_id")}
        delivery_note_id = as_uuid(payload.get("delivery_note_id"))
        delivery_lines: dict[uuid.UUID, DeliveryNoteLine] = {}
        if delivery_note_id:
            delivery = self.db.get(DeliveryNote, delivery_note_id)
            if delivery is None:
                raise NotFoundError("Delivery note not found")
            delivery_lines = {item.sales_order_line_id: item for item in delivery.lines if item.sales_order_line_id}

        lines_payload: list[dict[str, Any]] = []
        for line in order.lines:
            requested_line = requested.get(line.id)
            if requested_line is None and payload.get("lines"):
                continue
            outstanding = quantity(Decimal(line.ordered_quantity or 0) - Decimal(line.invoiced_quantity or 0))
            invoice_qty = quantity(requested_line.get("quantity", outstanding) if requested_line else outstanding)
            if invoice_qty <= 0:
                continue
            if invoice_qty > outstanding:
                raise BusinessRuleError(
                    "Invoice quantity exceeds the ordered quantity",
                    line=str(line.id),
                    outstanding=str(outstanding),
                )
            delivered_line = delivery_lines.get(line.id)
            lines_payload.append(
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "unit_id": line.unit_id,
                    "quantity": invoice_qty,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "tax_id": line.tax_id,
                    "warehouse_id": line.warehouse_id or order.warehouse_id,
                    "sales_order_line_id": line.id,
                    "delivery_note_line_id": delivered_line.id if delivered_line else None,
                    "unit_cost": delivered_line.unit_cost if delivered_line else None,
                    "project_id": line.project_id,
                    "cost_center_id": line.cost_center_id,
                }
            )
        if not lines_payload:
            raise BusinessRuleError("There is nothing left to invoice on this order")

        service = SalesInvoiceService(self.db, self.company_id, user_id=self.user_id)
        invoice = service.create(
            {
                "customer_id": order.customer_id,
                "sales_order_id": order.id,
                "delivery_note_id": delivery_note_id,
                "salesperson_id": order.salesperson_id,
                "branch_id": order.branch_id,
                "warehouse_id": order.warehouse_id,
                "project_id": order.project_id,
                "currency_code": order.currency_code,
                "payment_term_id": order.payment_term_id,
                "document_date": payload.get("document_date") or date.today(),
                "due_date": payload.get("due_date"),
                "commission_percent": order.commission_percent,
                "reference": payload.get("reference"),
                "notes": payload.get("notes"),
                "lines": lines_payload,
            },
            allow_credit_override=bool(payload.get("allow_credit_override", False)),
        )
        return invoice

    def refresh_fulfilment(self, order: SalesOrder) -> None:
        delivered = all(
            quantity(line.fulfilled_quantity) >= quantity(line.ordered_quantity) for line in order.lines
        )
        invoiced = all(quantity(line.invoiced_quantity) >= quantity(line.ordered_quantity) for line in order.lines)
        order.is_fully_delivered = bool(order.lines) and delivered
        order.is_fully_invoiced = bool(order.lines) and invoiced
        if order.is_fully_delivered and order.is_fully_invoiced:
            order.status = DocumentStatus.FULFILLED.value
        elif delivered or any(quantity(line.fulfilled_quantity) > 0 for line in order.lines):
            if order.status not in {DocumentStatus.FULFILLED.value}:
                order.status = DocumentStatus.PARTIALLY_FULFILLED.value
        self.db.flush()

    def record_delivery(self, order_line_id: uuid.UUID, delivered: Decimal) -> None:
        line = self.db.get(SalesOrderLine, order_line_id)
        if line is None:
            return
        line.fulfilled_quantity = quantity(Decimal(line.fulfilled_quantity or 0) + delivered)
        line.remaining_quantity = quantity(Decimal(line.ordered_quantity or 0) - Decimal(line.fulfilled_quantity or 0))
        self.db.flush()

    def record_invoice(self, order_line_id: uuid.UUID, invoiced: Decimal) -> None:
        line = self.db.get(SalesOrderLine, order_line_id)
        if line is None:
            return
        line.invoiced_quantity = quantity(Decimal(line.invoiced_quantity or 0) + invoiced)
        self.db.flush()


# --------------------------------------------------------------------------- #
# Delivery note
# --------------------------------------------------------------------------- #
class DeliveryNoteService(_SalesDocumentService):
    document_type = "delivery_note"
    model = DeliveryNote
    line_model = DeliveryNoteLine
    permission_entity = "delivery_note"
    inventory_direction = "out"

    def create(self, payload: dict[str, Any]) -> DeliveryNote:
        customer = self.get_customer(uuid.UUID(str(payload["customer_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products)
        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        delivery = DeliveryNote(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            customer_id=customer.id,
            sales_order_id=as_uuid(payload.get("sales_order_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            delivery_address=payload.get("delivery_address") or customer.address_line1,
            driver_name=payload.get("driver_name"),
            vehicle_number=payload.get("vehicle_number"),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            reference=payload.get("reference"),
            created_by_id=self.user_id,
        )
        self.db.add(delivery)
        self.db.flush()
        self.apply_line_rows(delivery, rows)
        self.apply_totals(delivery, totals, exchange_rate=exchange_rate)
        self.audit.log_create(delivery, entity_type="delivery_note", label=delivery.document_no)
        return delivery

    # ------------------------------------------------------------ inventory
    def apply_inventory(self, document: DeliveryNote) -> dict[str, Any]:
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = inventory.require_warehouse(document.warehouse_id)
        results = []
        for line in document.lines:
            if line.product_id is None:
                continue
            product = inventory.get_product(line.product_id)
            if not product.track_inventory or product.product_type == ProductType.SERVICE.value:
                continue
            move = StockMove(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id or warehouse_id,
                quantity=quantity(line.quantity),
                unit_id=line.unit_id,
                movement_type=MovementType.ISSUE,
                entry_date=document.document_date,
                location_id=line.location_id,
                batch_id=line.batch_id,
                serial_numbers=line.serial_numbers,
                reference_type="delivery_note",
                reference_id=document.id,
                reference_no=document.document_no,
                reference_line_id=line.id,
                party_type="customer",
                party_id=document.customer_id,
            )
            result = inventory.move(move)
            line.unit_cost = result.unit_cost
            results.append(result)
            self._attach_cost(line, result)
        self.db.flush()
        return {"moves": results, "total_cost": money(sum(item.total_cost for item in results))}

    @staticmethod
    def _attach_cost(line: DeliveryNoteLine, result) -> None:
        """Store the issued cost on the line (used by COGS posting)."""
        line.extra_data = {**(line.extra_data or {}), "unit_cost": str(result.unit_cost), "ledger_entry_id": str(result.ledger_entry.id)}

    def build_journal_lines(self, document: DeliveryNote, inventory_result: Any = None) -> list[EntryLine]:
        """Perpetual inventory: Dr COGS / Cr Inventory for the delivered cost."""
        if not inventory_result or not inventory_result.get("moves"):
            return []
        total_cost = money(inventory_result["total_cost"])
        if total_cost <= 0:
            return []
        cogs_account = self.posting.resolve_account(
            "cogs", document_type=self.document_type, fallback_code="5110"
        )
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        return [
            EntryLine(
                account_id=cogs_account.id,
                debit=total_cost,
                description=f"Cost of goods sold {document.document_no}",
                party_type="customer",
                party_id=document.customer_id,
                branch_id=document.branch_id,
            ),
            EntryLine(
                account_id=inventory_account.id,
                credit=total_cost,
                description=f"Inventory issued {document.document_no}",
                branch_id=document.branch_id,
            ),
        ]

    def after_post(self, document: DeliveryNote, inventory_result: Any = None, entry: Any = None) -> None:
        if document.sales_order_id:
            order_service = SalesOrderService(self.db, self.company_id, user_id=self.user_id)
            for line in document.lines:
                if line.sales_order_line_id:
                    order_service.record_delivery(line.sales_order_line_id, quantity(line.quantity))
            order = self.db.get(SalesOrder, document.sales_order_id)
            if order:
                order_service.refresh_fulfilment(order)
            self._update_project_cost(document, inventory_result)

    def _update_project_cost(self, document: DeliveryNote, inventory_result: Any) -> None:
        if not inventory_result:
            return
        order = self.db.get(SalesOrder, document.sales_order_id) if document.sales_order_id else None
        if order is None or order.project_id is None:
            return
        from app.models.projects import Project

        project = self.db.get(Project, order.project_id)
        if project is None:
            return
        project.actual_materials = money(
            Decimal(project.actual_materials or 0) + money(inventory_result.get("total_cost", 0))
        )
        self.db.flush()


# --------------------------------------------------------------------------- #
# Sales invoice
# --------------------------------------------------------------------------- #
class SalesInvoiceService(_SalesDocumentService):
    document_type = "sales_invoice"
    model = SalesInvoice
    line_model = SalesInvoiceLine
    permission_entity = "sales_invoice"

    def create(self, payload: dict[str, Any], *, allow_credit_override: bool = False) -> SalesInvoice:
        customer = self.get_customer(uuid.UUID(str(payload["customer_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products)

        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code") or customer.currency_code, document_date, self.company().base_currency_code
        )
        payment_term_id = as_uuid(payload.get("payment_term_id")) or customer.payment_term_id
        term_days = self.payment_term_days(payment_term_id) or int(customer.credit_days or 0)
        sales_channel = payload.get("sales_channel", "direct")

        if sales_channel != "pos" and not allow_credit_override:
            self.assert_credit_limit(customer, money(totals["total_amount"]))

        invoice = SalesInvoice(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            customer_id=customer.id,
            sales_order_id=as_uuid(payload.get("sales_order_id")),
            delivery_note_id=as_uuid(payload.get("delivery_note_id")),
            salesperson_id=as_uuid(payload.get("salesperson_id")) or self.user_id,
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            project_id=as_uuid(payload.get("project_id")),
            currency_code=payload.get("currency_code") or customer.currency_code,
            exchange_rate=exchange_rate,
            payment_term_id=payment_term_id,
            due_date=payload.get("due_date") or (document_date + timedelta(days=term_days) if term_days else None),
            sales_channel=sales_channel,
            commission_percent=_to_decimal(payload.get("commission_percent")),
            pos_shift_id=as_uuid(payload.get("pos_shift_id")),
            pos_terminal_id=as_uuid(payload.get("pos_terminal_id")),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            terms_and_conditions=payload.get("terms_and_conditions"),
            reference=payload.get("reference"),
            created_by_id=self.user_id,
        )
        self.db.add(invoice)
        self.db.flush()
        self.apply_line_rows(invoice, rows)
        self.apply_totals(
            invoice,
            totals,
            discount_amount=_to_decimal(payload.get("discount_amount")),
            other_charges=_to_decimal(payload.get("other_charges")),
            shipping_amount=_to_decimal(payload.get("shipping_amount")),
            exchange_rate=exchange_rate,
        )
        invoice.balance_amount = money(invoice.total_amount)
        self.calculate_commission(invoice)
        self.db.flush()
        self.audit.log_create(invoice, entity_type="sales_invoice", label=invoice.document_no)
        return invoice

    def calculate_commission(self, invoice: SalesInvoice) -> None:
        percent = _to_decimal(invoice.commission_percent)
        if percent <= 0:
            invoice.commission_amount = money(0)
        else:
            invoice.commission_amount = money(money(invoice.total_amount) * percent / Decimal("100"))
        self.db.flush()

    # ------------------------------------------------------------- inventory
    def apply_inventory(self, document: SalesInvoice) -> dict[str, Any]:
        if document.delivery_note_id:
            # Stock already left with the delivery note: never issue twice, just
            # carry the delivered cost so margin reporting stays accurate.
            total_cost = Decimal("0")
            delivery = self.db.get(DeliveryNote, document.delivery_note_id)
            delivery_lines = {item.id: item for item in delivery.lines} if delivery else {}
            for line in document.lines:
                source = delivery_lines.get(line.delivery_note_line_id) if line.delivery_note_line_id else None
                if source is None and delivery is not None:
                    source = next(
                        (item for item in delivery.lines if item.product_id == line.product_id), None
                    )
                if source is not None:
                    line.unit_cost = money(source.unit_cost)
                    total_cost += money(source.unit_cost) * quantity(line.quantity)
            document.total_cost = money(total_cost)
            document.gross_profit = money(Decimal(document.total_amount or 0) - document.total_cost)
            self.db.flush()
            return {"moves": [], "total_cost": document.total_cost, "skipped": "delivered"}
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = inventory.require_warehouse(document.warehouse_id)
        results = []
        for line in document.lines:
            if line.product_id is None:
                continue
            product = inventory.get_product(line.product_id)
            if not product.track_inventory or product.product_type == ProductType.SERVICE.value:
                continue
            move = StockMove(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id or warehouse_id,
                quantity=quantity(line.quantity),
                unit_id=line.unit_id,
                movement_type=MovementType.ISSUE,
                entry_date=document.document_date,
                batch_id=line.batch_id,
                serial_numbers=line.serial_numbers,
                location_id=line.location_id,
                reference_type="sales_invoice",
                reference_id=document.id,
                reference_no=document.document_no,
                reference_line_id=line.id,
                party_type="customer",
                party_id=document.customer_id,
            )
            result = inventory.move(move)
            line.unit_cost = result.unit_cost
            results.append(result)
        total_cost = money(sum(item.total_cost for item in results))
        document.total_cost = total_cost
        document.gross_profit = money(Decimal(document.total_amount or 0) - total_cost)
        self.db.flush()
        return {"moves": results, "total_cost": total_cost}

    # ------------------------------------------------------------ accounting
    def build_journal_lines(self, document: SalesInvoice, inventory_result: Any = None) -> list[EntryLine]:
        company_currency = self.company().base_currency_code
        receivable_account = self._customer_account(document.customer_id, "receivable_account_id", "ar_account", "1210")
        revenue_default = self._customer_account(document.customer_id, "revenue_account_id", "sales_revenue_account", "4110")
        tax_payable = self.posting.resolve_account("tax_payable", document_type=self.document_type, fallback_code="2210")
        discount_account = self.posting.resolve_account("discount", document_type=self.document_type, fallback_code="4120")

        lines: list[EntryLine] = []
        total_revenue = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")

        for line in document.lines:
            revenue_account_id = line.revenue_account_id or revenue_default.id
            net = money(line.net_amount)
            lines.append(
                EntryLine(
                    account_id=revenue_account_id,
                    credit=net,
                    description=line.description or f"Revenue {document.document_no}",
                    party_type="customer",
                    party_id=document.customer_id,
                    branch_id=document.branch_id,
                    cost_center_id=line.cost_center_id,
                    project_id=line.project_id,
                    warehouse_id=line.warehouse_id,
                    product_id=line.product_id,
                    tax_id=line.tax_id,
                    source_document_line_id=line.id,
                )
            )
            total_revenue += net
            if money(line.tax_amount) > 0:
                tax_account_id = self._tax_account_for_line(line, tax_payable.id)
                lines.append(
                    EntryLine(
                        account_id=tax_account_id,
                        credit=money(line.tax_amount),
                        description=f"Tax on {line.description or document.document_no}",
                        tax_id=line.tax_id,
                        source_document_line_id=line.id,
                        branch_id=document.branch_id,
                    )
                )
                total_tax += money(line.tax_amount)
            if money(line.discount_amount) > 0:
                lines.append(
                    EntryLine(
                        account_id=discount_account.id,
                        debit=money(line.discount_amount),
                        description="Sales discount",
                        source_document_line_id=line.id,
                        branch_id=document.branch_id,
                    )
                )
                total_discount += money(line.discount_amount)

        if money(document.discount_amount) > 0:
            lines.append(
                EntryLine(
                    account_id=discount_account.id,
                    debit=money(document.discount_amount),
                    description="Invoice discount",
                    branch_id=document.branch_id,
                )
            )
            total_discount += money(document.discount_amount)

        extra = money(document.other_charges) + money(document.shipping_amount)
        if extra > 0:
            shipping_account = self.posting.resolve_account(
                "shipping_revenue", document_type=self.document_type, fallback_code="4130"
            )
            lines.append(
                EntryLine(
                    account_id=shipping_account.id,
                    credit=extra,
                    description="Other charges and shipping",
                    branch_id=document.branch_id,
                )
            )
            total_revenue += extra

        receivable_total = money(document.total_amount)
        lines.append(
            EntryLine(
                account_id=receivable_account.id,
                debit=receivable_total,
                description=f"Invoice {document.document_no}",
                party_type="customer",
                party_id=document.customer_id,
                branch_id=document.branch_id,
                currency_code=document.currency_code,
                exchange_rate=Decimal(document.exchange_rate or 1),
            )
        )

        # Cost of goods sold for invoices that are not backed by a delivery.
        if inventory_result and inventory_result.get("moves"):
            total_cost = money(inventory_result["total_cost"])
            if total_cost > 0:
                cogs_account = self.posting.resolve_account("cogs", document_type=self.document_type, fallback_code="5110")
                inventory_account = self.posting.resolve_account(
                    "inventory", document_type=self.document_type, fallback_code="1310"
                )
                lines.append(
                    EntryLine(
                        account_id=cogs_account.id,
                        debit=total_cost,
                        description=f"Cost of goods sold {document.document_no}",
                        project_id=document.project_id,
                        branch_id=document.branch_id,
                    )
                )
                lines.append(
                    EntryLine(
                        account_id=inventory_account.id,
                        credit=total_cost,
                        description=f"Inventory issued {document.document_no}",
                        branch_id=document.branch_id,
                    )
                )
        if company_currency and document.currency_code == company_currency:
            document.exchange_rate = Decimal("1")
        self.db.flush()
        return lines

    def _customer_account(
        self, customer_id: uuid.UUID, attribute: str, fallback_role: str, fallback_code: str
    ):
        customer = self.db.get(Customer, customer_id)
        explicit = getattr(customer, attribute, None) if customer else None
        return self.posting.resolve_account(
            fallback_role, document_type=self.document_type, explicit_account_id=explicit, fallback_code=fallback_code
        )

    def _tax_account_for_line(self, line: SalesInvoiceLine, default_account_id: uuid.UUID) -> uuid.UUID:
        tax = self.tax_engine.get_tax(line.tax_id)
        if tax and (tax.sales_account_id or tax.purchase_account_id):
            return tax.sales_account_id or tax.purchase_account_id
        return default_account_id

    def after_post(self, document: SalesInvoice, inventory_result: Any = None, entry: Any = None) -> None:
        # Accounts receivable sub-ledger
        self.posting.post_customer_document(
            customer_id=document.customer_id,
            document_type="sales_invoice",
            document_id=document.id,
            document_no=document.document_no,
            document_date=document.document_date,
            amount=money(document.total_amount),
            is_debit=True,
            due_date=document.due_date,
            currency_code=document.currency_code,
            exchange_rate=Decimal(document.exchange_rate or 1),
            remarks=document.notes,
        )
        self.posting.refresh_payment_status(document)

        # Fulfilment tracking back on the order
        if document.sales_order_id:
            order_service = SalesOrderService(self.db, self.company_id, user_id=self.user_id)
            for line in document.lines:
                if line.sales_order_line_id:
                    order_service.record_invoice(line.sales_order_line_id, quantity(line.quantity))
            order = self.db.get(SalesOrder, document.sales_order_id)
            if order:
                order_service.refresh_fulfilment(order)

        if document.delivery_note_id:
            delivery = self.db.get(DeliveryNote, document.delivery_note_id)
            if delivery:
                delivery.is_invoiced = True
                delivery.invoice_id = document.id

        # Commission accrual
        if money(document.commission_amount) > 0 and document.salesperson_id:
            self.db.add(
                SalesCommission(
                    company_id=self.company_id,
                    salesperson_id=document.salesperson_id,
                    invoice_id=document.id,
                    period_start=document.document_date.replace(day=1),
                    period_end=document.document_date,
                    base_amount=money(document.total_amount),
                    commission_percent=_to_decimal(document.commission_percent),
                    commission_amount=money(document.commission_amount),
                    status=DocumentStatus.APPROVED.value,
                )
            )

        # Project profitability
        if document.project_id:
            from app.models.projects import Project

            project = self.db.get(Project, document.project_id)
            if project:
                project.invoiced_amount = money(Decimal(project.invoiced_amount or 0) + money(document.total_amount))
                self.db.flush()
        self.db.flush()


# --------------------------------------------------------------------------- #
# Credit note (sales return)
# --------------------------------------------------------------------------- #
class CreditNoteService(_SalesDocumentService):
    document_type = "credit_note"
    model = CreditNote
    line_model = CreditNoteLine
    permission_entity = "credit_note"

    def create(self, payload: dict[str, Any]) -> CreditNote:
        customer = self.get_customer(uuid.UUID(str(payload["customer_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products)
        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        credit_note = CreditNote(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            customer_id=customer.id,
            invoice_id=as_uuid(payload.get("invoice_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            return_reason=payload.get("return_reason"),
            is_inventory_returned=bool(payload.get("is_inventory_returned", True)),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(credit_note)
        self.db.flush()
        self.apply_line_rows(credit_note, rows)
        self.apply_totals(credit_note, totals, exchange_rate=exchange_rate)
        self.audit.log_create(credit_note, entity_type="credit_note", label=credit_note.document_no)
        return credit_note

    def apply_inventory(self, document: CreditNote) -> dict[str, Any]:
        if not document.is_inventory_returned:
            return {"moves": [], "total_cost": money(0)}
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = inventory.require_warehouse(document.warehouse_id)
        results = []
        for line in document.lines:
            if line.product_id is None:
                continue
            product = inventory.get_product(line.product_id)
            if not product.track_inventory or product.product_type == ProductType.SERVICE.value:
                continue
            move = StockMove(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id or warehouse_id,
                quantity=quantity(line.quantity),
                unit_id=line.unit_id,
                movement_type=MovementType.SALES_RETURN_IN,
                entry_date=document.document_date,
                unit_cost=line.unit_cost if line.unit_cost else None,
                batch_id=line.batch_id,
                serial_numbers=line.serial_numbers,
                reference_type="credit_note",
                reference_id=document.id,
                reference_no=document.document_no,
                reference_line_id=line.id,
                party_type="customer",
                party_id=document.customer_id,
            )
            result = inventory.move(move)
            line.unit_cost = result.unit_cost
            results.append(result)
        self.db.flush()
        return {"moves": results, "total_cost": money(sum(item.total_cost for item in results))}

    def build_journal_lines(self, document: CreditNote, inventory_result: Any = None) -> list[EntryLine]:
        receivable_account = self.posting.resolve_account("ar", document_type=self.document_type, fallback_code="1210")
        revenue_default = self.posting.resolve_account(
            "sales_revenue", document_type=self.document_type, fallback_code="4110"
        )
        tax_payable = self.posting.resolve_account("tax_payable", document_type=self.document_type, fallback_code="2210")
        lines: list[EntryLine] = [
            EntryLine(
                account_id=receivable_account.id,
                credit=money(document.total_amount),
                description=f"Credit note {document.document_no}",
                party_type="customer",
                party_id=document.customer_id,
                branch_id=document.branch_id,
            )
        ]
        for line in document.lines:
            lines.append(
                EntryLine(
                    account_id=line.account_id or revenue_default.id,
                    debit=money(line.net_amount),
                    description=f"Sales return {document.document_no}",
                    party_type="customer",
                    party_id=document.customer_id,
                    product_id=line.product_id,
                    tax_id=line.tax_id,
                    source_document_line_id=line.id,
                    branch_id=document.branch_id,
                )
            )
            if money(line.tax_amount) > 0:
                lines.append(
                    EntryLine(
                        account_id=self._tax_account_for_line(line, tax_payable.id),
                        debit=money(line.tax_amount),
                        description="Tax reversal",
                        tax_id=line.tax_id,
                        branch_id=document.branch_id,
                    )
                )
        if inventory_result and inventory_result.get("moves"):
            total_cost = money(inventory_result["total_cost"])
            if total_cost > 0:
                cogs_account = self.posting.resolve_account("cogs", document_type=self.document_type, fallback_code="5110")
                inventory_account = self.posting.resolve_account(
                    "inventory", document_type=self.document_type, fallback_code="1310"
                )
                lines.append(
                    EntryLine(
                        account_id=inventory_account.id,
                        debit=total_cost,
                        description=f"Inventory returned {document.document_no}",
                        branch_id=document.branch_id,
                    )
                )
                lines.append(
                    EntryLine(
                        account_id=cogs_account.id,
                        credit=total_cost,
                        description="Cost of goods returned",
                        branch_id=document.branch_id,
                    )
                )
        return lines

    def _tax_account_for_line(self, line: CreditNoteLine, default_account_id: uuid.UUID) -> uuid.UUID:
        tax = self.tax_engine.get_tax(line.tax_id)
        if tax and (tax.sales_account_id or tax.purchase_account_id):
            return tax.sales_account_id or tax.purchase_account_id
        return default_account_id

    def after_post(self, document: CreditNote, inventory_result: Any = None, entry: Any = None) -> None:
        self.posting.post_customer_document(
            customer_id=document.customer_id,
            document_type="credit_note",
            document_id=document.id,
            document_no=document.document_no,
            document_date=document.document_date,
            amount=money(document.total_amount),
            is_debit=False,
            currency_code=document.currency_code,
            exchange_rate=Decimal(document.exchange_rate or 1),
            remarks=document.return_reason,
        )


# --------------------------------------------------------------------------- #
# POS
# --------------------------------------------------------------------------- #
class PosShiftService(BaseDocumentService):
    document_type = "pos_shift"
    model = PosShift
    line_model = None
    permission_module = "sales"
    permission_entity = "pos_shift"
    requires_lines = False

    def get_terminal(self, terminal_id: uuid.UUID) -> PosTerminal:
        terminal = self.db.execute(
            select(PosTerminal).where(PosTerminal.company_id == self.company_id, PosTerminal.id == terminal_id)
        ).scalars().first()
        if terminal is None:
            raise NotFoundError("POS terminal not found")
        return terminal

    def open_shift(
        self, *, terminal_id: uuid.UUID, cashier_id: uuid.UUID | None = None, opening_cash: Decimal = Decimal("0")
    ) -> PosShift:
        terminal = self.get_terminal(terminal_id)
        existing = self.db.execute(
            select(PosShift).where(
                PosShift.company_id == self.company_id,
                PosShift.terminal_id == terminal.id,
                PosShift.status == ShiftStatus.OPEN.value,
            )
        ).scalars().first()
        if existing is not None:
            raise BusinessRuleError("This terminal already has an open shift", shift_no=existing.shift_no)
        shift = PosShift(
            company_id=self.company_id,
            shift_no=self.next_number(branch_id=terminal.branch_id),
            terminal_id=terminal.id,
            cashier_id=cashier_id or self.user_id,
            branch_id=terminal.branch_id,
            opened_at=datetime.now(UTC),
            opening_cash=money(opening_cash),
            expected_cash=money(opening_cash),
            status=ShiftStatus.OPEN.value,
        )
        self.db.add(shift)
        self.db.flush()
        self.audit.log_create(shift, entity_type="pos_shift", label=shift.shift_no)
        return shift

    def current_shift(self, *, terminal_id: uuid.UUID | None = None, cashier_id: uuid.UUID | None = None) -> PosShift | None:
        stmt = select(PosShift).where(
            PosShift.company_id == self.company_id, PosShift.status == ShiftStatus.OPEN.value
        )
        if terminal_id:
            stmt = stmt.where(PosShift.terminal_id == terminal_id)
        if cashier_id:
            stmt = stmt.where(PosShift.cashier_id == cashier_id)
        return self.db.execute(stmt.order_by(PosShift.opened_at.desc())).scalars().first()

    def register_sale(self, shift: PosShift, invoice: SalesInvoice, payments: Sequence[dict[str, Any]]) -> None:
        cash_total = Decimal("0")
        card_total = Decimal("0")
        wallet_total = Decimal("0")
        for payment in payments:
            method = str(payment.get("payment_method", PaymentMethod.CASH.value))
            amount = money(payment.get("amount", 0))
            if method == PaymentMethod.CASH.value:
                cash_total += amount
            elif method == PaymentMethod.CARD.value:
                card_total += amount
            else:
                wallet_total += amount
        shift.total_sales = money(Decimal(shift.total_sales or 0) + money(invoice.total_amount))
        shift.total_cash_sales = money(Decimal(shift.total_cash_sales or 0) + cash_total)
        shift.total_card_sales = money(Decimal(shift.total_card_sales or 0) + card_total)
        shift.total_wallet_sales = money(Decimal(shift.total_wallet_sales or 0) + wallet_total)
        shift.total_discounts = money(
            Decimal(shift.total_discounts or 0) + money(invoice.discount_amount) + money(0)
        )
        shift.invoice_count = int(shift.invoice_count or 0) + 1
        shift.expected_cash = money(Decimal(shift.expected_cash or 0) + cash_total)
        self.db.flush()

    def register_return(self, shift: PosShift, amount: Decimal, *, cash: bool = True) -> None:
        shift.total_returns = money(Decimal(shift.total_returns or 0) + money(amount))
        if cash:
            shift.expected_cash = money(Decimal(shift.expected_cash or 0) - money(amount))
        self.db.flush()

    def cash_movement(
        self, shift: PosShift, *, movement_type: str, amount: Decimal, reason: str | None = None
    ) -> PosCashMovement:
        if shift.status != ShiftStatus.OPEN.value:
            raise BusinessRuleError("The shift is closed")
        amount = money(amount)
        movement = PosCashMovement(
            company_id=self.company_id,
            shift_id=shift.id,
            movement_type=movement_type,
            amount=amount,
            reason=reason,
            created_by_id=self.user_id,
        )
        self.db.add(movement)
        delta = amount if movement_type in {"cash_in", "pickup"} else -amount
        shift.expected_cash = money(Decimal(shift.expected_cash or 0) + delta)
        self.db.flush()
        return movement

    def close_shift(self, shift_id: uuid.UUID, *, counted_cash: Decimal, notes: str | None = None) -> PosShift:
        shift = self.get_document(shift_id)
        if shift.status != ShiftStatus.OPEN.value:
            raise BusinessRuleError("This shift is already closed")
        counted = money(counted_cash)
        shift.counted_cash = counted
        shift.cash_difference = money(counted - money(shift.expected_cash))
        shift.closed_at = datetime.now(UTC)
        shift.status = ShiftStatus.CLOSED.value
        shift.notes = notes
        shift.z_report_json = self.z_report(shift)
        self.db.flush()
        self.audit.log_action(AuditAction.CLOSE, shift, entity_type="pos_shift", remarks="shift closed")
        return shift

    def z_report(self, shift: PosShift) -> dict[str, Any]:
        return {
            "shift_no": shift.shift_no,
            "cashier_id": str(shift.cashier_id),
            "terminal_id": str(shift.terminal_id),
            "opened_at": shift.opened_at.isoformat() if shift.opened_at else None,
            "closed_at": shift.closed_at.isoformat() if shift.closed_at else None,
            "opening_cash": str(money(shift.opening_cash)),
            "expected_cash": str(money(shift.expected_cash)),
            "counted_cash": str(money(shift.counted_cash)) if shift.counted_cash is not None else None,
            "difference": str(money(shift.cash_difference)),
            "total_sales": str(money(shift.total_sales)),
            "total_cash_sales": str(money(shift.total_cash_sales)),
            "total_card_sales": str(money(shift.total_card_sales)),
            "total_wallet_sales": str(money(shift.total_wallet_sales)),
            "total_returns": str(money(shift.total_returns)),
            "total_discounts": str(money(shift.total_discounts)),
            "invoice_count": shift.invoice_count,
        }

    def reconcile(
        self, shift_id: uuid.UUID, *, counted_cash: Decimal, difference_reason: str | None = None
    ) -> PosShift:
        """Close the shift *and* post the cash difference to accounting."""
        shift = self.close_shift(shift_id, counted_cash=counted_cash, notes=difference_reason)
        shift.difference_reason = difference_reason
        if abs(money(shift.cash_difference)) > Decimal("0.01"):
            terminal = self.get_terminal(shift.terminal_id)
            cash_account_id = terminal.cash_account_id
            if cash_account_id:
                cash_account = self.db.get(CashAccount, cash_account_id)
                if cash_account:
                    variance_account = self.posting.resolve_account(
                        "cash_over_short", document_type="pos_shift", fallback_code="5160"
                    )
                    difference = money(shift.cash_difference)
                    lines = (
                        [
                            EntryLine(account_id=cash_account.account_id, debit=difference, description="Cash over"),
                            EntryLine(account_id=variance_account.id, credit=difference, description="Cash over"),
                        ]
                        if difference > 0
                        else [
                            EntryLine(account_id=variance_account.id, debit=abs(difference), description="Cash short"),
                            EntryLine(account_id=cash_account.account_id, credit=abs(difference), description="Cash short"),
                        ]
                    )
                    entry = self.posting.build_entry(
                        context=self._posting_context(shift), lines=lines, entry_type="pos_shift", user_id=self.user_id
                    )
                    shift.journal_entry_id = entry.id
        shift.status = ShiftStatus.RECONCILED.value
        self.db.flush()
        return shift


class PosSaleService(BaseDocumentService):
    """POS sale: creates and posts an invoice plus its split payments."""

    document_type = "sales_invoice"
    model = SalesInvoice
    line_model = SalesInvoiceLine
    permission_module = "sales"
    permission_entity = "pos_sale"
    prices_include_tax = True

    def create_sale(self, payload: dict[str, Any]) -> SalesInvoice:
        terminal_service = PosShiftService(self.db, self.company_id, user_id=self.user_id)
        terminal = terminal_service.get_terminal(uuid.UUID(str(payload["terminal_id"])))
        shift_id = as_uuid(payload.get("shift_id"))
        if shift_id:
            shift = self.db.get(PosShift, uuid.UUID(str(shift_id)))
        else:
            shift = terminal_service.current_shift(terminal_id=terminal.id, cashier_id=self.user_id)
        if shift is None or shift.status != ShiftStatus.OPEN.value:
            raise BusinessRuleError("No open shift found for this terminal; open a shift first")

        customer_id = as_uuid(payload.get("customer_id")) or terminal.default_customer_id
        if customer_id is None:
            raise ValidationFailure("A customer is required for a POS sale (configure a walk-in customer on the terminal)")

        invoice_service = SalesInvoiceService(self.db, self.company_id, user_id=self.user_id)
        invoice = invoice_service.create(
            {
                "customer_id": customer_id,
                "branch_id": terminal.branch_id,
                "warehouse_id": terminal.warehouse_id or as_uuid(payload.get("warehouse_id")),
                "currency_code": payload.get("currency_code"),
                "document_date": date.today(),
                "sales_channel": "pos",
                "pos_shift_id": shift.id,
                "pos_terminal_id": terminal.id,
                "discount_amount": payload.get("discount_amount"),
                "notes": payload.get("notes"),
                "lines": payload.get("lines", []),
            },
            allow_credit_override=True,
        )

        payments = payload.get("payments") or [
            {"payment_method": PaymentMethod.CASH.value, "amount": invoice.total_amount}
        ]
        paid_total = sum((money(item.get("amount", 0)) for item in payments), Decimal("0.00"))
        if paid_total < money(invoice.total_amount) - Decimal("0.01"):
            raise BusinessRuleError(
                "The tendered amount is less than the invoice total",
                total=str(money(invoice.total_amount)),
                tendered=str(money(paid_total)),
            )
        for payment in payments:
            tender = money(payment.get("tendered_amount", payment.get("amount", 0)))
            amount = money(payment.get("amount", 0))
            self.db.add(
                PosPayment(
                    company_id=self.company_id,
                    invoice_id=invoice.id,
                    shift_id=shift.id,
                    payment_method=str(payment.get("payment_method", PaymentMethod.CASH.value)),
                    amount=amount,
                    tendered_amount=tender,
                    change_amount=money(max(Decimal("0"), tender - amount)),
                    reference=payment.get("reference"),
                    card_type=payment.get("card_type"),
                    terminal_reference=payment.get("terminal_reference"),
                )
            )
        invoice.paid_amount = money(paid_total)
        invoice.balance_amount = money(Decimal(invoice.total_amount or 0) - paid_total)
        self.db.flush()

        self.post(invoice, allow_draft=True)
        terminal_service.register_sale(shift, invoice, payments)
        self.pay_pos_invoice(invoice, payments, terminal)
        return invoice

    def pay_pos_invoice(self, invoice: SalesInvoice, payments: Sequence[dict[str, Any]], terminal: PosTerminal) -> None:
        """Book the cash/card leg of a POS sale."""
        total = money(invoice.total_amount)
        cash_account = self.db.get(CashAccount, terminal.cash_account_id) if terminal.cash_account_id else None
        default_cash = self.posting.resolve_account("cash", document_type="pos_sale", fallback_code="1110")
        receivable = self.posting.resolve_account("ar", document_type="pos_sale", fallback_code="1210")
        card_account = self.posting.resolve_account("card_clearing", document_type="pos_sale", fallback_code="1120")
        lines: list[EntryLine] = [EntryLine(account_id=receivable.id, credit=total, description=f"POS settlement {invoice.document_no}")]
        for payment in payments:
            method = str(payment.get("payment_method", PaymentMethod.CASH.value))
            amount = money(payment.get("amount", 0))
            if amount <= 0:
                continue
            account_id = (
                cash_account.account_id
                if cash_account is not None and method == PaymentMethod.CASH.value
                else (default_cash.id if method == PaymentMethod.CASH.value else card_account.id)
            )
            lines.append(
                EntryLine(
                    account_id=account_id,
                    debit=amount,
                    description=f"POS {method}",
                    party_type="customer",
                    party_id=invoice.customer_id,
                    branch_id=invoice.branch_id,
                )
            )
        entry = self.posting.build_entry(
            context=self._posting_context(invoice),
            lines=lines,
            entry_type="pos_payment",
            user_id=self.user_id,
        )
        invoice.payment_status = PaymentStatus.PAID.value
        invoice.is_fully_paid = True
        self.posting.refresh_payment_status(invoice)
        self.posting.post_customer_document(
            customer_id=invoice.customer_id,
            document_type="pos_receipt",
            document_id=entry.id,
            document_no=invoice.document_no,
            document_date=invoice.document_date,
            amount=money(invoice.paid_amount),
            is_debit=False,
        )
        self.db.flush()


class PosTerminalService(BaseDocumentService):
    document_type = "pos_terminal"
    model = PosTerminal
    line_model = None
    permission_module = "sales"
    permission_entity = "pos_terminal"
    requires_lines = False

    def quick_setup(self, payload: dict[str, Any]) -> PosTerminal:
        """Create a terminal together with its dedicated cash account."""
        from app.services.accounting_service import ChartOfAccountsService

        branch_id = as_uuid(payload.get("branch_id"))
        cash_account_id = as_uuid(payload.get("cash_account_id"))
        if cash_account_id is None:
            chart = ChartOfAccountsService(self.db, self.company_id)
            cash_account = chart.create_cash_account(
                name=payload.get("name", "POS Cash"),
                code=f"POS-{payload.get('code', '01')}",
                branch_id=branch_id,
                opening_balance=Decimal("0"),
            )
            cash_account_id = cash_account.id
        terminal = PosTerminal(
            company_id=self.company_id,
            code=payload["code"],
            name=payload["name"],
            branch_id=branch_id,
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            cash_account_id=cash_account_id,
            default_customer_id=as_uuid(payload.get("default_customer_id")),
            price_list_id=as_uuid(payload.get("price_list_id")),
            receipt_footer=payload.get("receipt_footer"),
            allow_discount=bool(payload.get("allow_discount", True)),
            max_discount_percent=_to_decimal(payload.get("max_discount_percent") or 100),
            settings_json=payload.get("settings_json") or {},
        )
        self.db.add(terminal)
        self.db.flush()
        return terminal


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))
