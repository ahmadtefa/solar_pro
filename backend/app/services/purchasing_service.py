"""Purchasing services: request -> RFQ -> quotation -> order -> receipt ->
invoice -> debit note, including supplier prices, comparison and evaluation.

Accounting strategy
-------------------
* **Goods receipt** debits inventory and credits *Goods Received Not Invoiced*
  (GRNI), i.e. the liability appears the moment goods physically arrive.
* **Purchase invoice** clears GRNI (for received quantities) and records the
  VAT input; quantities not yet received are booked straight to inventory.
* **Debit note** (return) reverses both the inventory and the payable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, DocumentStatus, MovementType, ProductType
from app.core.coercion import as_uuid
from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.masterdata import Product, Supplier, SupplierPriceHistory, SupplierProduct
from app.models.platform import Company, PaymentTerm
from app.models.purchasing import (
    DebitNote,
    DebitNoteLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
    Rfq,
    RfqLine,
    RfqSupplier,
    SupplierEvaluation,
    SupplierQuotation,
    SupplierQuotationLine,
)
from app.services.audit_service import AuditContext
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


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


class _PurchaseDocumentService(BaseDocumentService):
    permission_module = "purchasing"

    def company(self) -> Company:
        company = self.db.get(Company, self.company_id)
        if company is None:
            raise NotFoundError("Company not found")
        return company

    def get_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = self.db.execute(
            select(Supplier).where(Supplier.company_id == self.company_id, Supplier.id == supplier_id)
        ).scalars().first()
        if supplier is None:
            raise NotFoundError("Supplier not found", supplier_id=str(supplier_id))
        return supplier

    def payment_term_days(self, payment_term_id: uuid.UUID | None) -> int:
        if not payment_term_id:
            return 0
        term = self.db.execute(
            select(PaymentTerm).where(PaymentTerm.company_id == self.company_id, PaymentTerm.id == payment_term_id)
        ).scalars().first()
        return int(term.days) if term else 0

    def outstanding_payable(self, supplier_id: uuid.UUID) -> Decimal:
        value = self.db.execute(
            select(func.coalesce(func.sum(PurchaseInvoice.balance_amount), 0)).where(
                PurchaseInvoice.company_id == self.company_id,
                PurchaseInvoice.supplier_id == supplier_id,
                PurchaseInvoice.status == DocumentStatus.POSTED.value,
                PurchaseInvoice.deleted_at.is_(None),
            )
        ).scalar_one()
        return money(value)

    def record_supplier_price(
        self,
        *,
        supplier_id: uuid.UUID,
        product_id: uuid.UUID,
        unit_price: Decimal,
        quantity_value: Decimal,
        price_date: date,
        currency_code: str | None = None,
        source_document_type: str | None = None,
        source_document_id: uuid.UUID | None = None,
    ) -> None:
        self.db.add(
            SupplierPriceHistory(
                company_id=self.company_id,
                supplier_id=supplier_id,
                product_id=product_id,
                unit_price=money(unit_price),
                quantity=quantity_value,
                currency_code=currency_code,
                price_date=price_date,
                source_document_type=source_document_type,
                source_document_id=source_document_id,
            )
        )
        catalogue = self.db.execute(
            select(SupplierProduct).where(
                SupplierProduct.company_id == self.company_id,
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == product_id,
            )
        ).scalars().first()
        if catalogue is None:
            catalogue = SupplierProduct(
                company_id=self.company_id,
                supplier_id=supplier_id,
                product_id=product_id,
                last_price=money(unit_price),
                last_purchase_date=price_date,
            )
            self.db.add(catalogue)
        else:
            catalogue.last_price = money(unit_price)
            catalogue.last_purchase_date = price_date
        product = self.db.get(Product, product_id)
        if product is not None and money(unit_price) > 0:
            product.cost_price = money(unit_price)
        self.db.flush()


# --------------------------------------------------------------------------- #
# Purchase request
# --------------------------------------------------------------------------- #
class PurchaseRequestService(_PurchaseDocumentService):
    document_type = "purchase_request"
    model = PurchaseRequest
    line_model = PurchaseRequestLine
    permission_entity = "purchase_request"

    def create(self, payload: dict[str, Any]) -> PurchaseRequest:
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        for row in rows:
            row["approved_quantity"] = Decimal("0")
        document_date = payload.get("document_date") or date.today()
        request = PurchaseRequest(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            project_id=as_uuid(payload.get("project_id")),
            cost_center_id=as_uuid(payload.get("cost_center_id")),
            requested_by_id=as_uuid(payload.get("requested_by_id")) or self.user_id,
            required_date=payload.get("required_date"),
            priority=payload.get("priority", "normal"),
            justification=payload.get("justification"),
            notes=payload.get("notes"),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(request)
        self.db.flush()
        self.apply_line_rows(request, rows)
        self.apply_totals(request, totals)
        self.audit.log_create(request, entity_type="purchase_request", label=request.document_no)
        return request


# --------------------------------------------------------------------------- #
# RFQ
# --------------------------------------------------------------------------- #
class RfqService(_PurchaseDocumentService):
    document_type = "rfq"
    model = Rfq
    line_model = RfqLine
    permission_entity = "rfq"

    def create_from_request(self, request_id: uuid.UUID, supplier_ids: Sequence[uuid.UUID]) -> Rfq:
        request = PurchaseRequestService(self.db, self.company_id, user_id=self.user_id).get_document(request_id)
        if not supplier_ids:
            raise ValidationFailure("Select at least one supplier to request quotations from")
        rfq = Rfq(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=request.branch_id),
            document_date=date.today(),
            purchase_request_id=request.id,
            buyer_id=request.requested_by_id,
            branch_id=request.branch_id,
            closing_date=date.today() + timedelta(days=7),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(rfq)
        self.db.flush()
        for line in request.lines:
            self.db.add(
                RfqLine(
                    company_id=self.company_id,
                    rfq_id=rfq.id,
                    sequence_no=line.sequence_no,
                    product_id=line.product_id,
                    description=line.description,
                    unit_id=line.unit_id,
                    quantity=line.quantity,
                    base_quantity=line.base_quantity,
                    unit_price=line.unit_price,
                    required_date=line.required_date,
                )
            )
        for supplier_id in supplier_ids:
            self.db.add(
                RfqSupplier(
                    company_id=self.company_id,
                    rfq_id=rfq.id,
                    supplier_id=supplier_id,
                    sent_at=datetime.now(UTC),
                )
            )
        self.db.flush()
        self.audit.log_create(rfq, entity_type="rfq", label=rfq.document_no)
        return rfq


class SupplierQuotationService(_PurchaseDocumentService):
    document_type = "supplier_quotation"
    model = SupplierQuotation
    line_model = SupplierQuotationLine
    permission_entity = "supplier_quotation"

    def create(self, payload: dict[str, Any]) -> SupplierQuotation:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        document_date = payload.get("document_date") or date.today()
        quotation = SupplierQuotation(
            company_id=self.company_id,
            document_no=self.next_number(),
            document_date=document_date,
            supplier_id=supplier.id,
            rfq_id=as_uuid(payload.get("rfq_id")),
            supplier_reference=payload.get("supplier_reference"),
            valid_until=payload.get("valid_until"),
            lead_time_days=int(payload.get("lead_time_days") or 0),
            currency_code=payload.get("currency_code"),
            notes=payload.get("notes"),
            status=DocumentStatus.DRAFT.value,
            created_by_id=self.user_id,
        )
        self.db.add(quotation)
        self.db.flush()
        self.apply_line_rows(quotation, rows)
        self.apply_totals(quotation, totals)
        self.audit.log_create(quotation, entity_type="supplier_quotation", label=quotation.document_no)
        return quotation

    def compare(self, rfq_id: uuid.UUID) -> dict[str, Any]:
        """Supplier comparison matrix for an RFQ (used by the procurement UI)."""
        rfq = self.db.execute(
            select(Rfq).where(Rfq.company_id == self.company_id, Rfq.id == rfq_id)
        ).scalars().first()
        if rfq is None:
            raise NotFoundError("RFQ not found")
        quotations = list(
            self.db.execute(
                select(SupplierQuotation).where(
                    SupplierQuotation.company_id == self.company_id,
                    SupplierQuotation.rfq_id == rfq.id,
                    SupplierQuotation.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        product_ids = {line.product_id for line in rfq.lines if line.product_id}
        matrix: dict[str, Any] = {
            "rfq": {"id": rfq.id, "document_no": rfq.document_no, "lines": []},
            "quotations": [],
        }
        for line in rfq.lines:
            matrix["rfq"]["lines"].append(
                {
                    "line_id": line.id,
                    "product_id": line.product_id,
                    "description": line.description,
                    "quantity": str(line.quantity),
                }
            )
        for quotation in quotations:
            supplier = self.db.get(Supplier, quotation.supplier_id)
            prices = {line.product_id: line for line in quotation.lines}
            matrix["quotations"].append(
                {
                    "quotation_id": quotation.id,
                    "document_no": quotation.document_no,
                    "supplier_id": quotation.supplier_id,
                    "supplier_name": supplier.name if supplier else None,
                    "total_amount": str(money(quotation.total_amount)),
                    "lead_time_days": quotation.lead_time_days,
                    "valid_until": quotation.valid_until,
                    "is_selected": quotation.is_selected,
                    "lines": [
                        {
                            "product_id": product_id,
                            "unit_price": str(prices[product_id].unit_price) if product_id in prices else None,
                            "line_total": str(prices[product_id].line_total) if product_id in prices else None,
                        }
                        for product_id in product_ids
                    ],
                }
            )
        return matrix

    def award(self, quotation_id: uuid.UUID) -> PurchaseOrder:
        quotation = self.get_document(quotation_id)
        if quotation.converted_order_id:
            raise BusinessRuleError("This quotation was already converted into a purchase order")
        supplier = self.get_supplier(quotation.supplier_id)
        order_service = PurchaseOrderService(self.db, self.company_id, user_id=self.user_id)
        order = order_service.create(
            {
                "supplier_id": supplier.id,
                "supplier_quotation_id": quotation.id,
                "purchase_request_id": quotation.extra_data.get("purchase_request_id") if quotation.extra_data else None,
                "currency_code": quotation.currency_code,
                "document_date": date.today(),
                "lines": [
                    {
                        "product_id": line.product_id,
                        "description": line.description,
                        "unit_id": line.unit_id,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                        "discount_percent": line.discount_percent,
                        "tax_id": line.tax_id,
                    }
                    for line in quotation.lines
                ],
            }
        )
        quotation.is_selected = True
        quotation.converted_order_id = order.id
        quotation.status = DocumentStatus.CLOSED.value
        if quotation.rfq_id:
            rfq = self.db.get(Rfq, quotation.rfq_id)
            if rfq:
                rfq.awarded_quotation_id = quotation.id
                rfq.awarded_at = datetime.now(UTC)
                rfq.status = DocumentStatus.CLOSED.value
        self.db.flush()
        return order


# --------------------------------------------------------------------------- #
# Purchase order
# --------------------------------------------------------------------------- #
class PurchaseOrderService(_PurchaseDocumentService):
    document_type = "purchase_order"
    model = PurchaseOrder
    line_model = PurchaseOrderLine
    permission_entity = "purchase_order"

    def create(self, payload: dict[str, Any]) -> PurchaseOrder:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        if supplier.is_blocked:
            raise BusinessRuleError(f"Supplier {supplier.name} is blocked", reason=supplier.block_reason)
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        for row in rows:
            row["ordered_quantity"] = row["quantity"]
            row["remaining_quantity"] = row["quantity"]

        document_date = payload.get("document_date") or date.today()
        payment_term_id = as_uuid(payload.get("payment_term_id")) or supplier.payment_term_id
        term_days = self.payment_term_days(payment_term_id) or int(supplier.credit_days or 0)
        order = PurchaseOrder(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            supplier_id=supplier.id,
            supplier_quotation_id=as_uuid(payload.get("supplier_quotation_id")),
            purchase_request_id=as_uuid(payload.get("purchase_request_id")),
            buyer_id=as_uuid(payload.get("buyer_id")) or self.user_id,
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            project_id=as_uuid(payload.get("project_id")),
            currency_code=payload.get("currency_code") or supplier.currency_code,
            payment_term_id=payment_term_id,
            due_date=document_date + timedelta(days=term_days) if term_days else None,
            expected_date=payload.get("expected_date"),
            supplier_reference=payload.get("supplier_reference"),
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
        )
        self.audit.log_create(order, entity_type="purchase_order", label=order.document_no)
        return order

    def approve(self, document: Any) -> Any:  # type: ignore[override]
        order = super().approve(document)
        for line in document.lines:
            if line.product_id and money(line.unit_price) > 0:
                self.record_supplier_price(
                    supplier_id=document.supplier_id,
                    product_id=line.product_id,
                    unit_price=line.unit_price,
                    quantity_value=quantity(line.quantity),
                    price_date=document.document_date,
                    currency_code=document.currency_code,
                    source_document_type="purchase_order",
                    source_document_id=document.id,
                )
        return order

    def create_receipt(self, order_id: uuid.UUID, payload: dict[str, Any]) -> GoodsReceipt:
        order = self.get_document(order_id)
        if order.status not in {
            DocumentStatus.APPROVED.value,
            DocumentStatus.PARTIALLY_FULFILLED.value,
            DocumentStatus.DRAFT.value,
        }:
            raise BusinessRuleError("Goods can only be received against an approved order")
        requested = {uuid.UUID(str(line["order_line_id"])): line for line in payload.get("lines", []) if line.get("order_line_id")}
        lines_payload: list[dict[str, Any]] = []
        for line in order.lines:
            requested_line = requested.get(line.id)
            if requested_line is None and payload.get("lines"):
                continue
            receive_qty = quantity(requested_line.get("quantity", line.remaining_quantity) if requested_line else line.remaining_quantity)
            if receive_qty <= 0:
                continue
            if receive_qty > quantity(line.remaining_quantity):
                raise BusinessRuleError(
                    "Receipt quantity exceeds the outstanding order quantity",
                    line=str(line.id),
                    remaining=str(line.remaining_quantity),
                )
            lines_payload.append(
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "unit_id": line.unit_id,
                    "quantity": receive_qty,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "tax_id": line.tax_id,
                    "warehouse_id": line.warehouse_id or order.warehouse_id,
                    "batch_number": (requested_line or {}).get("batch_number"),
                    "expiry_date": (requested_line or {}).get("expiry_date"),
                    "purchase_order_line_id": line.id,
                }
            )
        if not lines_payload:
            raise BusinessRuleError("There is nothing left to receive on this order")
        service = GoodsReceiptService(self.db, self.company_id, user_id=self.user_id)
        return service.create(
            {
                "supplier_id": order.supplier_id,
                "purchase_order_id": order.id,
                "branch_id": order.branch_id,
                "warehouse_id": order.warehouse_id,
                "project_id": order.project_id,
                "currency_code": order.currency_code,
                "document_date": payload.get("document_date") or date.today(),
                "supplier_delivery_note": payload.get("supplier_delivery_note"),
                "notes": payload.get("notes"),
                "lines": lines_payload,
            }
        )

    def create_invoice(self, order_id: uuid.UUID, payload: dict[str, Any]) -> PurchaseInvoice:
        order = self.get_document(order_id)
        requested = {uuid.UUID(str(line["order_line_id"])): line for line in payload.get("lines", []) if line.get("order_line_id")}
        goods_receipt_id = as_uuid(payload.get("goods_receipt_id"))
        received_lines: dict[uuid.UUID, GoodsReceiptLine] = {}
        if goods_receipt_id:
            receipt = self.db.get(GoodsReceipt, goods_receipt_id)
            if receipt is None:
                raise NotFoundError("Goods receipt not found")
            received_lines = {item.purchase_order_line_id: item for item in receipt.lines if item.purchase_order_line_id}
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
                raise BusinessRuleError("Invoice quantity exceeds the ordered quantity", line=str(line.id))
            receipt_line = received_lines.get(line.id)
            supplied_receipt_line_id = as_uuid((requested_line or {}).get("goods_receipt_line_id"))
            lines_payload.append(
                {
                    "product_id": line.product_id,
                    "description": line.description,
                    "unit_id": line.unit_id,
                    "quantity": invoice_qty,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "tax_id": line.tax_id,
                    "purchase_order_line_id": line.id,
                    "goods_receipt_line_id": supplied_receipt_line_id or (receipt_line.id if receipt_line else None),
                    "warehouse_id": line.warehouse_id or order.warehouse_id,
                    "project_id": line.project_id,
                    "cost_center_id": line.cost_center_id,
                }
            )
        if not lines_payload:
            raise BusinessRuleError("There is nothing left to invoice on this order")
        service = PurchaseInvoiceService(self.db, self.company_id, user_id=self.user_id)
        return service.create(
            {
                "supplier_id": order.supplier_id,
                "purchase_order_id": order.id,
                "branch_id": order.branch_id,
                "warehouse_id": order.warehouse_id,
                "project_id": order.project_id,
                "currency_code": order.currency_code,
                "payment_term_id": order.payment_term_id,
                "document_date": payload.get("document_date") or date.today(),
                "supplier_invoice_no": payload.get("supplier_invoice_no"),
                "supplier_invoice_date": payload.get("supplier_invoice_date"),
                "goods_receipt_id": goods_receipt_id,
                "due_date": payload.get("due_date"),
                "reference": payload.get("reference"),
                "notes": payload.get("notes"),
                "lines": lines_payload,
            }
        )

    def record_receipt(self, order_line_id: uuid.UUID, received: Decimal) -> None:
        line = self.db.get(PurchaseOrderLine, order_line_id)
        if line is None:
            return
        line.fulfilled_quantity = quantity(Decimal(line.fulfilled_quantity or 0) + received)
        line.remaining_quantity = quantity(Decimal(line.ordered_quantity or 0) - Decimal(line.fulfilled_quantity or 0))
        self.db.flush()

    def record_invoice(self, order_line_id: uuid.UUID, invoiced: Decimal) -> None:
        line = self.db.get(PurchaseOrderLine, order_line_id)
        if line is None:
            return
        line.invoiced_quantity = quantity(Decimal(line.invoiced_quantity or 0) + invoiced)
        self.db.flush()

    def refresh_fulfilment(self, order: PurchaseOrder) -> None:
        received = all(quantity(line.fulfilled_quantity) >= quantity(line.ordered_quantity) for line in order.lines)
        invoiced = all(quantity(line.invoiced_quantity) >= quantity(line.ordered_quantity) for line in order.lines)
        order.is_fully_received = bool(order.lines) and received
        order.is_fully_invoiced = bool(order.lines) and invoiced
        if received and invoiced:
            order.status = DocumentStatus.FULFILLED.value
        elif received or any(quantity(line.fulfilled_quantity) > 0 for line in order.lines):
            order.status = DocumentStatus.PARTIALLY_FULFILLED.value
        self.db.flush()


# --------------------------------------------------------------------------- #
# Goods receipt
# --------------------------------------------------------------------------- #
class GoodsReceiptService(_PurchaseDocumentService):
    document_type = "goods_receipt"
    model = GoodsReceipt
    line_model = GoodsReceiptLine
    permission_entity = "goods_receipt"
    inventory_direction = "in"

    def create(self, payload: dict[str, Any]) -> GoodsReceipt:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        for row in rows:
            # Inbound cost is the purchase price net of line discount.
            row["unit_cost"] = row["unit_price"] - (
                (row["unit_price"] * Decimal(row.get("discount_percent") or 0) / Decimal("100"))
            )
        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code"), document_date, self.company().base_currency_code
        )
        receipt = GoodsReceipt(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            supplier_id=supplier.id,
            purchase_order_id=as_uuid(payload.get("purchase_order_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            exchange_rate=exchange_rate,
            supplier_delivery_note=payload.get("supplier_delivery_note"),
            received_by_id=as_uuid(payload.get("received_by_id")) or self.user_id,
            inspection_status=payload.get("inspection_status", "pending"),
            inspection_notes=payload.get("inspection_notes"),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(receipt)
        self.db.flush()
        self.apply_line_rows(receipt, rows)
        self.apply_totals(receipt, totals, exchange_rate=exchange_rate)
        self.audit.log_create(receipt, entity_type="goods_receipt", label=receipt.document_no)
        return receipt

    def apply_inventory(self, document: GoodsReceipt) -> dict[str, Any]:
        inventory = InventoryService(self.db, self.company_id)
        warehouse_id = inventory.require_warehouse(document.warehouse_id)
        results = []
        for line in document.lines:
            if line.product_id is None:
                continue
            product = inventory.get_product(line.product_id)
            if not product.track_inventory or product.product_type == ProductType.SERVICE.value:
                continue
            unit_cost = line.unit_cost or line.unit_price
            move = StockMove(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id or warehouse_id,
                quantity=quantity(line.quantity),
                unit_id=line.unit_id,
                unit_cost=unit_cost,
                movement_type=MovementType.RECEIPT,
                entry_date=document.document_date,
                batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                batch_id=line.batch_id,
                reference_type="goods_receipt",
                reference_id=document.id,
                reference_no=document.document_no,
                reference_line_id=line.id,
                party_type="supplier",
                party_id=document.supplier_id,
            )
            result = inventory.move(move)
            line.unit_cost = result.unit_cost
            results.append(result)
        self.db.flush()
        return {"moves": results, "total_cost": money(sum(item.total_cost for item in results))}

    def build_journal_lines(self, document: GoodsReceipt, inventory_result: Any = None) -> list[EntryLine]:
        total_cost = money(inventory_result["total_cost"]) if inventory_result else money(0)
        if total_cost <= 0:
            return []
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        grni_account = self.posting.resolve_account("grni", document_type=self.document_type, fallback_code="2130")
        return [
            EntryLine(
                account_id=inventory_account.id,
                debit=total_cost,
                description=f"Goods received {document.document_no}",
                party_type="supplier",
                party_id=document.supplier_id,
                branch_id=document.branch_id,
            ),
            EntryLine(
                account_id=grni_account.id,
                credit=total_cost,
                description=f"Goods received not invoiced {document.document_no}",
                party_type="supplier",
                party_id=document.supplier_id,
                branch_id=document.branch_id,
            ),
        ]

    def after_post(self, document: GoodsReceipt, inventory_result: Any = None, entry: Any = None) -> None:
        if document.purchase_order_id:
            service = PurchaseOrderService(self.db, self.company_id, user_id=self.user_id)
            for line in document.lines:
                if line.purchase_order_line_id:
                    service.record_receipt(line.purchase_order_line_id, quantity(line.quantity))
                    if line.product_id:
                        self.record_supplier_price(
                            supplier_id=document.supplier_id,
                            product_id=line.product_id,
                            unit_price=line.unit_price,
                            quantity_value=quantity(line.quantity),
                            price_date=document.document_date,
                            currency_code=document.currency_code,
                            source_document_type="goods_receipt",
                            source_document_id=document.id,
                        )
            order = self.db.get(PurchaseOrder, document.purchase_order_id)
            if order:
                service.refresh_fulfilment(order)
        else:
            order = self.db.get(PurchaseOrder, document.purchase_order_id) if document.purchase_order_id else None
        # Goods receipts have no project of their own: they inherit the order's project.
        project_id = getattr(document, "project_id", None) or (order.project_id if order else None)
        if project_id and inventory_result:
            from app.models.projects import Project

            project = self.db.get(Project, project_id)
            if project:
                project.actual_materials = money(
                    Decimal(project.actual_materials or 0) + money(inventory_result.get("total_cost", 0))
                )
                self.db.flush()


# --------------------------------------------------------------------------- #
# Purchase invoice
# --------------------------------------------------------------------------- #
class PurchaseInvoiceService(_PurchaseDocumentService):
    document_type = "purchase_invoice"
    model = PurchaseInvoice
    line_model = PurchaseInvoiceLine
    permission_entity = "purchase_invoice"

    def create(self, payload: dict[str, Any]) -> PurchaseInvoice:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        if supplier.is_blocked:
            raise BusinessRuleError(f"Supplier {supplier.name} is blocked", reason=supplier.block_reason)
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        document_date = payload.get("document_date") or date.today()
        exchange_rate = self.resolve_exchange_rate(
            payload.get("currency_code") or supplier.currency_code, document_date, self.company().base_currency_code
        )
        payment_term_id = as_uuid(payload.get("payment_term_id")) or supplier.payment_term_id
        term_days = self.payment_term_days(payment_term_id) or int(supplier.credit_days or 0)
        invoice = PurchaseInvoice(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            supplier_id=supplier.id,
            purchase_order_id=as_uuid(payload.get("purchase_order_id")),
            goods_receipt_id=as_uuid(payload.get("goods_receipt_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            department_id=as_uuid(payload.get("department_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            project_id=as_uuid(payload.get("project_id")),
            currency_code=payload.get("currency_code") or supplier.currency_code,
            exchange_rate=exchange_rate,
            payment_term_id=payment_term_id,
            due_date=payload.get("due_date") or (document_date + timedelta(days=term_days) if term_days else None),
            supplier_invoice_no=payload.get("supplier_invoice_no"),
            supplier_invoice_date=payload.get("supplier_invoice_date"),
            withholding_tax_amount=_to_decimal(payload.get("withholding_tax_amount")),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
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
        self.db.flush()
        self.audit.log_create(invoice, entity_type="purchase_invoice", label=invoice.document_no)
        return invoice

    def build_journal_lines(self, document: PurchaseInvoice, inventory_result: Any = None) -> list[EntryLine]:
        payable = self._supplier_account(document.supplier_id, "payable_account_id", "ap_account", "2110")
        grni = self.posting.resolve_account("grni", document_type=self.document_type, fallback_code="2130")
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        tax_receivable = self.posting.resolve_account(
            "tax_receivable", document_type=self.document_type, fallback_code="1410"
        )
        expense_default = self._supplier_account(
            document.supplier_id, "expense_account_id", "purchase_expense", "5130"
        )
        discount_account = self.posting.resolve_account(
            "purchase_discount", document_type=self.document_type, fallback_code="5140"
        )

        lines: list[EntryLine] = [
            EntryLine(
                account_id=payable.id,
                credit=money(document.total_amount),
                description=f"Supplier invoice {document.document_no}",
                party_type="supplier",
                party_id=document.supplier_id,
                branch_id=document.branch_id,
                currency_code=document.currency_code,
                exchange_rate=Decimal(document.exchange_rate or 1),
            )
        ]
        for line in document.lines:
            net = money(line.net_amount)
            product = self.db.get(Product, line.product_id) if line.product_id else None
            if product is not None and product.track_inventory and product.product_type != ProductType.SERVICE.value:
                raw_account_id = line.extra_data.get("inventory_account_id") if line.extra_data else None
                debit_account_id = as_uuid(raw_account_id) or product.inventory_account_id or inventory_account.id
                # Received quantities are already in inventory via the GRN (clearing GRNI).
                received = money(line.unit_price * quantity(line.quantity)) if line.goods_receipt_line_id else Decimal("0")
                if received > 0:
                    lines.append(
                        EntryLine(
                            account_id=grni.id,
                            debit=min(received, net),
                            description=f"GRNI clearing {document.document_no}",
                            party_type="supplier",
                            party_id=document.supplier_id,
                            product_id=line.product_id,
                            source_document_line_id=line.id,
                            branch_id=document.branch_id,
                        )
                    )
                    if net > received:
                        lines.append(
                            EntryLine(
                                account_id=debit_account_id,
                                debit=net - received,
                                description=f"Additional cost {document.document_no}",
                                product_id=line.product_id,
                                source_document_line_id=line.id,
                                branch_id=document.branch_id,
                            )
                        )
                else:
                    lines.append(
                        EntryLine(
                            account_id=debit_account_id,
                            debit=net,
                            description=line.description or f"Purchase {document.document_no}",
                            product_id=line.product_id,
                            warehouse_id=line.warehouse_id,
                            project_id=line.project_id,
                            cost_center_id=line.cost_center_id,
                            source_document_line_id=line.id,
                            branch_id=document.branch_id,
                        )
                    )
            else:
                account_id = line.expense_account_id or expense_default.id
                lines.append(
                    EntryLine(
                        account_id=account_id,
                        debit=net,
                        description=line.description or f"Purchase {document.document_no}",
                        project_id=line.project_id,
                        cost_center_id=line.cost_center_id,
                        product_id=line.product_id,
                        source_document_line_id=line.id,
                        branch_id=document.branch_id,
                    )
                )
            if money(line.tax_amount) > 0:
                tax = self.tax_engine.get_tax(line.tax_id)
                tax_account_id = (tax.purchase_account_id or tax.sales_account_id) if tax else None
                lines.append(
                    EntryLine(
                        account_id=tax_account_id or tax_receivable.id,
                        debit=money(line.tax_amount),
                        description="Input tax",
                        tax_id=line.tax_id,
                        source_document_line_id=line.id,
                        branch_id=document.branch_id,
                    )
                )
            if money(line.discount_amount) > 0:
                lines.append(
                    EntryLine(
                        account_id=discount_account.id,
                        credit=money(line.discount_amount),
                        description="Purchase discount",
                        branch_id=document.branch_id,
                    )
                )
        if money(document.discount_amount) > 0:
            lines.append(
                EntryLine(
                    account_id=discount_account.id,
                    credit=money(document.discount_amount),
                    description="Invoice discount",
                    branch_id=document.branch_id,
                )
            )
        if money(document.withholding_tax_amount) > 0:
            withholding = self.posting.resolve_account(
                "withholding_tax", document_type=self.document_type, fallback_code="2220"
            )
            lines.append(
                EntryLine(
                    account_id=withholding.id,
                    debit=money(document.withholding_tax_amount),
                    description="Withholding tax",
                    party_type="supplier",
                    party_id=document.supplier_id,
                    branch_id=document.branch_id,
                )
            )
        return lines

    def _supplier_account(self, supplier_id: uuid.UUID, attribute: str, role: str, fallback_code: str):
        supplier = self.db.get(Supplier, supplier_id)
        explicit = getattr(supplier, attribute, None) if supplier else None
        return self.posting.resolve_account(
            role, document_type=self.document_type, explicit_account_id=explicit, fallback_code=fallback_code
        )

    def after_post(self, document: PurchaseInvoice, inventory_result: Any = None, entry: Any = None) -> None:
        self.posting.post_supplier_document(
            supplier_id=document.supplier_id,
            document_type="purchase_invoice",
            document_id=document.id,
            document_no=document.document_no,
            document_date=document.document_date,
            amount=money(document.total_amount),
            is_credit=True,
            due_date=document.due_date,
            currency_code=document.currency_code,
            exchange_rate=Decimal(document.exchange_rate or 1),
        )
        self.posting.refresh_payment_status(document)
        if document.purchase_order_id:
            service = PurchaseOrderService(self.db, self.company_id, user_id=self.user_id)
            for line in document.lines:
                if line.purchase_order_line_id:
                    service.record_invoice(line.purchase_order_line_id, quantity(line.quantity))
            order = self.db.get(PurchaseOrder, document.purchase_order_id)
            if order:
                service.refresh_fulfilment(order)
        if document.goods_receipt_id:
            receipt = self.db.get(GoodsReceipt, document.goods_receipt_id)
            if receipt:
                receipt.is_invoiced = True
                receipt.invoice_id = document.id
        if document.project_id:
            from app.models.projects import Project

            project = self.db.get(Project, document.project_id)
            if project:
                project.actual_expenses = money(Decimal(project.actual_expenses or 0) + money(document.subtotal))
                self.db.flush()


class DebitNoteService(_PurchaseDocumentService):
    document_type = "debit_note"
    model = DebitNote
    line_model = DebitNoteLine
    permission_entity = "debit_note"
    inventory_direction = "out"

    def create(self, payload: dict[str, Any]) -> DebitNote:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        lines_input = payload.get("lines", [])
        products = _products_map(self.db, self.company_id, lines_input)
        rows, totals = self.build_lines(lines_input, product_lookup=products, purchase=True)
        for row in rows:
            row["unit_cost"] = row["unit_price"]
        document_date = payload.get("document_date") or date.today()
        note = DebitNote(
            company_id=self.company_id,
            document_no=self.next_number(branch_id=as_uuid(payload.get("branch_id"))),
            document_date=document_date,
            supplier_id=supplier.id,
            purchase_invoice_id=as_uuid(payload.get("purchase_invoice_id")),
            goods_receipt_id=as_uuid(payload.get("goods_receipt_id")),
            branch_id=as_uuid(payload.get("branch_id")),
            warehouse_id=as_uuid(payload.get("warehouse_id")),
            currency_code=payload.get("currency_code"),
            return_reason=payload.get("return_reason"),
            is_inventory_returned=bool(payload.get("is_inventory_returned", True)),
            status=DocumentStatus.DRAFT.value,
            notes=payload.get("notes"),
            created_by_id=self.user_id,
        )
        self.db.add(note)
        self.db.flush()
        self.apply_line_rows(note, rows)
        self.apply_totals(note, totals)
        self.audit.log_create(note, entity_type="debit_note", label=note.document_no)
        return note

    def apply_inventory(self, document: DebitNote) -> dict[str, Any]:
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
                movement_type=MovementType.PURCHASE_RETURN_OUT,
                entry_date=document.document_date,
                batch_id=line.batch_id,
                reference_type="debit_note",
                reference_id=document.id,
                reference_no=document.document_no,
                reference_line_id=line.id,
                party_type="supplier",
                party_id=document.supplier_id,
            )
            result = inventory.move(move)
            line.unit_cost = result.unit_cost
            results.append(result)
        self.db.flush()
        return {"moves": results, "total_cost": money(sum(item.total_cost for item in results))}

    def build_journal_lines(self, document: DebitNote, inventory_result: Any = None) -> list[EntryLine]:
        payable = self.posting.resolve_account("ap", document_type=self.document_type, fallback_code="2110")
        inventory_account = self.posting.resolve_account(
            "inventory", document_type=self.document_type, fallback_code="1310"
        )
        tax_receivable = self.posting.resolve_account(
            "tax_receivable", document_type=self.document_type, fallback_code="1410"
        )
        expense_default = self.posting.resolve_account(
            "purchase_expense", document_type=self.document_type, fallback_code="5130"
        )
        lines: list[EntryLine] = [
            EntryLine(
                account_id=payable.id,
                debit=money(document.total_amount),
                description=f"Purchase return {document.document_no}",
                party_type="supplier",
                party_id=document.supplier_id,
                branch_id=document.branch_id,
            )
        ]
        for line in document.lines:
            product = self.db.get(Product, line.product_id) if line.product_id else None
            account_id = (
                (product.inventory_account_id or inventory_account.id)
                if product is not None and product.track_inventory and product.product_type != ProductType.SERVICE.value
                else (line.account_id or expense_default.id)
            )
            lines.append(
                EntryLine(
                    account_id=account_id,
                    credit=money(line.net_amount),
                    description=line.description or f"Purchase return {document.document_no}",
                    product_id=line.product_id,
                    source_document_line_id=line.id,
                    branch_id=document.branch_id,
                )
            )
            if money(line.tax_amount) > 0:
                tax = self.tax_engine.get_tax(line.tax_id)
                tax_account_id = (tax.purchase_account_id or tax.sales_account_id) if tax else None
                lines.append(
                    EntryLine(
                        account_id=tax_account_id or tax_receivable.id,
                        credit=money(line.tax_amount),
                        description="Input tax reversal",
                        tax_id=line.tax_id,
                        branch_id=document.branch_id,
                    )
                )
        return lines

    def after_post(self, document: DebitNote, inventory_result: Any = None, entry: Any = None) -> None:
        self.posting.post_supplier_document(
            supplier_id=document.supplier_id,
            document_type="debit_note",
            document_id=document.id,
            document_no=document.document_no,
            document_date=document.document_date,
            amount=money(document.total_amount),
            is_credit=False,
            currency_code=document.currency_code,
            exchange_rate=Decimal(document.exchange_rate or 1),
            remarks=document.return_reason,
        )


class SupplierEvaluationService(_PurchaseDocumentService):
    document_type = "supplier_evaluation"
    model = SupplierEvaluation
    line_model = None
    permission_entity = "supplier_evaluation"
    requires_lines = False

    def evaluate(self, payload: dict[str, Any]) -> SupplierEvaluation:
        supplier = self.get_supplier(uuid.UUID(str(payload["supplier_id"])))
        quality = _to_decimal(payload.get("quality_score"))
        delivery = _to_decimal(payload.get("delivery_score"))
        price = _to_decimal(payload.get("price_score"))
        service_score = _to_decimal(payload.get("service_score"))
        overall = (quality + delivery + price + service_score) / Decimal("4")
        evaluation = SupplierEvaluation(
            company_id=self.company_id,
            supplier_id=supplier.id,
            evaluation_date=payload.get("evaluation_date") or date.today(),
            period_start=payload.get("period_start"),
            period_end=payload.get("period_end"),
            quality_score=quality,
            delivery_score=delivery,
            price_score=price,
            service_score=service_score,
            overall_score=overall.quantize(Decimal("0.0001")),
            evaluated_by_id=self.user_id,
            comments=payload.get("comments"),
        )
        self.db.add(evaluation)
        supplier.rating = overall
        self.db.flush()
        return evaluation
