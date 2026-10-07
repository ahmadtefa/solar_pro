"""Shared document lifecycle engine.

All transactional documents (sales, purchasing, treasury, inventory, HR, ...)
inherit the same status machine, line calculation, permission guard and audit
behaviour from :class:`BaseDocumentService`.  Concrete services implement the
business specific parts: inventory effects, journal construction and
fulfilment tracking.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.coercion import as_decimal, as_uuid
from app.core.enums import AuditAction, DocumentStatus
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError, ValidationFailure
from app.models.accounting import JournalEntry
from app.models.platform import Company, ExchangeRate, Tax
from app.services.audit_service import AuditContext, AuditService
from app.services.numbering_service import NumberingService
from app.services.posting_service import PostingService, money
from app.services.tax_engine import TaxEngine

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DocumentStatus.DRAFT.value: {DocumentStatus.SUBMITTED.value, DocumentStatus.APPROVED.value, DocumentStatus.CANCELLED.value, DocumentStatus.POSTED.value},
    DocumentStatus.SUBMITTED.value: {DocumentStatus.APPROVED.value, DocumentStatus.REJECTED.value, DocumentStatus.CANCELLED.value, DocumentStatus.DRAFT.value},
    DocumentStatus.APPROVED.value: {DocumentStatus.POSTED.value, DocumentStatus.CANCELLED.value, DocumentStatus.PARTIALLY_FULFILLED.value, DocumentStatus.FULFILLED.value},
    DocumentStatus.REJECTED.value: {DocumentStatus.DRAFT.value, DocumentStatus.CANCELLED.value},
    DocumentStatus.POSTED.value: {DocumentStatus.DRAFT.value, DocumentStatus.CANCELLED.value, DocumentStatus.PARTIALLY_FULFILLED.value, DocumentStatus.FULFILLED.value, DocumentStatus.CLOSED.value},
    DocumentStatus.PARTIALLY_FULFILLED.value: {DocumentStatus.FULFILLED.value, DocumentStatus.CLOSED.value, DocumentStatus.POSTED.value},
    DocumentStatus.FULFILLED.value: {DocumentStatus.CLOSED.value, DocumentStatus.POSTED.value},
    DocumentStatus.CANCELLED.value: set(),
    DocumentStatus.CLOSED.value: {DocumentStatus.POSTED.value},
}

#: Statuses in which a document can still be edited.
EDITABLE_STATUSES = {DocumentStatus.DRAFT.value, DocumentStatus.REJECTED.value}


class BaseDocumentService:
    """Common behaviour for every business document service."""

    document_type: str = "document"
    model: type[Any]
    line_model: type[Any] | None = None
    line_relationship: str = "lines"
    permission_entity: str = "document"
    permission_module: str = "core"
    prices_include_tax: bool = False
    requires_lines: bool = True
    inventory_direction: str | None = None  # "in" | "out" | None
    default_tax_type: str = "sales"

    def __init__(
        self,
        db: Session,
        company_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        audit_context: AuditContext | None = None,
    ) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        context = audit_context or AuditContext(company_id=company_id, user_id=user_id)
        context.company_id = context.company_id or company_id
        context.user_id = context.user_id or user_id
        self.audit = AuditService(db, context)
        self.posting = PostingService(db, company_id, self.audit)
        self.tax_engine = TaxEngine(db, company_id)
        self._numbering: NumberingService | None = None

    # ----------------------------------------------------------------- basics
    @property
    def numbering(self) -> NumberingService:
        if self._numbering is None:
            self._numbering = NumberingService(self.db, self.company_id)
        return self._numbering

    def permission(self, action: str) -> str:
        return f"{self.permission_module}.{self.permission_entity}.{action}"

    def get_document(self, document_id: uuid.UUID) -> Any:
        document = self.db.execute(
            select(self.model).where(self.model.company_id == self.company_id, self.model.id == document_id)
        ).scalars().first()
        if document is None:
            raise NotFoundError(f"{self.document_type.replace('_', ' ').title()} not found", id=str(document_id))
        return document

    def list_documents(self, *criteria: Any, limit: int = 100) -> list[Any]:
        stmt = select(self.model).where(self.model.company_id == self.company_id)
        if criteria:
            stmt = stmt.where(*criteria)
        # Most documents expose ``document_date``; models with a bespoke
        # lifecycle (e.g. production orders) only guarantee ``created_at``.
        document_date = getattr(self.model, "document_date", None)
        ordering = [document_date.desc()] if document_date is not None else []
        stmt = stmt.order_by(*ordering, self.model.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().unique().all())

    def next_number(self, *, branch_id: uuid.UUID | None = None) -> str:
        return self.numbering.next_number(self.document_type, branch_id=branch_id)

    # ------------------------------------------------------------- exchange rate
    def resolve_exchange_rate(
        self, currency_code: str | None, document_date: date, company_currency: str | None = None
    ) -> Decimal:
        if not currency_code or (company_currency and currency_code == company_currency):
            return Decimal("1")
        rate = self.db.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.company_id == self.company_id,
                ExchangeRate.currency_code == currency_code,
                ExchangeRate.is_active.is_(True),
                ExchangeRate.effective_from <= document_date,
            )
            .order_by(ExchangeRate.effective_from.desc())
        ).scalars().first()
        if rate is None:
            raise BusinessRuleError(
                f"No exchange rate configured for {currency_code} on {document_date.isoformat()}",
                currency_code=currency_code,
            )
        return Decimal(rate.rate)

    # -------------------------------------------------------------- line math
    def calculate_line(
        self,
        *,
        quantity: Decimal | int | str | float = 0,
        unit_price: Decimal | int | str | float = 0,
        discount_percent: Decimal | int | str | float = 0,
        discount_amount: Decimal | int | str | float = 0,
        tax: Tax | None = None,
        prices_include_tax: bool | None = None,
        unit_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> dict[str, Decimal]:
        """Compute net / tax / total for a single document line."""
        quantity = Decimal(quantity or 0).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        unit_price = Decimal(unit_price or 0)
        gross = money(quantity * unit_price)
        discount = money(discount_amount or 0)
        if discount_percent:
            discount = money(discount + (gross * Decimal(discount_percent) / Decimal("100")))
        discount = min(discount, gross)
        net_before_tax = money(gross - discount)

        inclusive = self.prices_include_tax if prices_include_tax is None else prices_include_tax
        breakdown = self.tax_engine.apply(net_before_tax, tax=tax, prices_include_tax=inclusive)
        net = money(breakdown.net_amount)
        tax_amount = money(breakdown.tax_amount)
        total = money(net + tax_amount)

        base_quantity = quantity
        if product_id and unit_id:
            from app.services.inventory_service import InventoryService

            base_quantity = InventoryService(self.db, self.company_id).to_base_quantity(
                product_id, quantity, unit_id
            )

        return {
            "quantity": quantity,
            "base_quantity": base_quantity,
            "unit_price": unit_price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            "discount_amount": discount,
            "net_amount": net,
            "tax_amount": tax_amount,
            "line_total": total,
        }

    def build_lines(
        self,
        payload_lines: Sequence[dict[str, Any]],
        *,
        product_lookup: dict[uuid.UUID, Any] | None = None,
        purchase: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
        """Validate and calculate every line, returning rows plus document totals."""
        if self.requires_lines and not payload_lines:
            raise ValidationFailure("The document requires at least one line")

        computed: list[dict[str, Any]] = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for index, raw in enumerate(payload_lines, start=1):
            product = None
            product_id = raw.get("product_id")
            if product_id and product_lookup:
                product = product_lookup.get(uuid.UUID(str(product_id)))
            tax = None
            tax_id = raw.get("tax_id")
            if tax_id:
                tax = self.tax_engine.require_tax(uuid.UUID(str(tax_id)))
            elif product is not None:
                tax = self.tax_engine.tax_for_product(product, purchase=purchase)

            values = self.calculate_line(
                quantity=raw.get("quantity", 0),
                unit_price=raw.get("unit_price", raw.get("price", 0)),
                discount_percent=raw.get("discount_percent", 0),
                discount_amount=raw.get("discount_amount", 0),
                tax=tax,
                prices_include_tax=raw.get("prices_include_tax", self.prices_include_tax),
                unit_id=raw.get("unit_id"),
                product_id=uuid.UUID(str(product_id)) if product_id else None,
            )
            row = dict(raw)
            row.update(values)
            row["sequence_no"] = raw.get("sequence_no", index)
            row["tax_rate"] = Decimal(tax.rate) if tax else Decimal(raw.get("tax_rate", 0) or 0)
            if raw.get("unit_cost") is not None:
                row["unit_cost"] = Decimal(str(raw["unit_cost"]))
            computed.append(row)

            subtotal += values["net_amount"] + values["discount_amount"]
            discount_total += values["discount_amount"]
            tax_total += values["tax_amount"]
            grand_total += values["line_total"]

        totals = {
            "subtotal": money(subtotal),
            "discount_amount": money(discount_total),
            "tax_amount": money(tax_total),
            "total_amount": money(grand_total),
        }
        return computed, totals

    def apply_totals(
        self,
        document: Any,
        totals: dict[str, Decimal],
        *,
        other_charges: Decimal | None = None,
        shipping_amount: Decimal | None = None,
        discount_amount: Decimal | None = None,
        exchange_rate: Decimal | None = None,
    ) -> None:
        header_discount = money(discount_amount if discount_amount is not None else document.discount_amount or 0)
        other = money(other_charges if other_charges is not None else document.other_charges or 0)
        shipping = money(shipping_amount if shipping_amount is not None else document.shipping_amount or 0)
        subtotal = money(totals["subtotal"])
        tax = money(totals["tax_amount"])
        total = money(subtotal - header_discount + tax + other + shipping)
        document.subtotal = subtotal
        document.discount_amount = header_discount
        document.tax_amount = tax
        document.other_charges = other
        document.shipping_amount = shipping
        document.total_amount = total
        rate = Decimal(exchange_rate or getattr(document, "exchange_rate", 1) or 1)
        document.total_amount_base = money(total * rate)
        if hasattr(document, "balance_amount"):
            document.balance_amount = money(total - money(getattr(document, "paid_amount", 0)))
        self.db.flush()

    # ------------------------------------------------------------- life cycle
    def ensure_editable(self, document: Any) -> None:
        if getattr(document, "is_locked", False):
            raise BusinessRuleError("This document is locked and cannot be modified")
        status = getattr(document, "status", DocumentStatus.DRAFT.value)
        if status not in EDITABLE_STATUSES:
            raise BusinessRuleError(
                f"A document with status '{status}' cannot be edited. Create a correction instead.",
                status=status,
            )

    def company(self) -> Company:
        """The company (tenant) row this service operates on."""
        company = self.db.get(Company, self.company_id)
        if company is None:
            raise NotFoundError("Company not found")
        return company

    def can_transition(self, document: Any, target: str) -> bool:
        current = getattr(document, "status", DocumentStatus.DRAFT.value)
        return target in ALLOWED_TRANSITIONS.get(current, set())

    def transition(
        self,
        document: Any,
        target: str,
        *,
        reason: str | None = None,
        action: AuditAction | None = None,
    ) -> Any:
        if not self.can_transition(document, target):
            raise BusinessRuleError(
                f"Invalid status transition from '{getattr(document, 'status', None)}' to '{target}'",
                current=getattr(document, "status", None),
                target=target,
            )
        previous = document.status
        document.status = target
        now = datetime.now(UTC)
        user_id = self.user_id
        match target:
            case DocumentStatus.SUBMITTED.value:
                document.submitted_by_id = user_id
                document.submitted_at = now
            case DocumentStatus.APPROVED.value:
                document.approved_by_id = user_id
                document.approved_at = now
            case DocumentStatus.REJECTED.value:
                document.rejected_by_id = user_id
                document.rejected_at = now
                document.rejection_reason = reason
            case DocumentStatus.POSTED.value:
                document.posted_by_id = user_id
                document.posted_at = now
            case DocumentStatus.CANCELLED.value:
                document.cancelled_by_id = user_id
                document.cancelled_at = now
                document.cancel_reason = reason
        self.db.flush()
        self.audit.record(
            action=action or _ACTION_FOR_STATUS.get(target, AuditAction.UPDATE),
            entity_type=self.document_type,
            entity_id=getattr(document, "id", None),
            entity_label=getattr(document, "document_no", None),
            old_values={"status": previous},
            new_values={"status": target},
            remarks=reason,
        )
        return document

    # -------------------------------------------------------- posting hooks
    def validate_posting(self, document: Any) -> None:
        """Override for document specific posting checks."""

    def apply_inventory(self, document: Any) -> Any:
        """Override to move stock; return whatever the journal builder needs."""
        return None

    def build_journal_lines(self, document: Any, inventory_result: Any = None) -> list[Any]:
        """Override to return ``EntryLine`` objects; empty list = no accounting."""
        return []

    def after_post(self, document: Any, inventory_result: Any = None, entry: Any = None) -> None:
        """Override for fulfilment bookkeeping (order quantities, sub-ledgers...)."""

    def after_unpost(self, document: Any, entry: Any = None) -> None:
        """Override to roll back post-time side effects (idempotent by design)."""

    def reverse_inventory(self, document: Any, entry: Any = None) -> None:
        """Undo the stock effects of a posted document.

        Every stock movement carries ``reference_type``/``reference_id``, so the
        default implementation reverses the ledger rows of this document.  The
        reversal is idempotent: reversed rows are flagged and never reversed
        twice, which keeps unpost/re-post cycles safe.
        """
        from app.services.inventory_service import InventoryService

        reference_type = getattr(document, "inventory_reference_type", None) or self.document_type
        document_id = getattr(document, "id", None)
        if document_id is None:
            return
        InventoryService(self.db, self.company_id).reverse_document_moves(
            reference_type,
            document_id,
            entry_date=getattr(document, "document_date", None) or date.today(),
            reason=f"Reversal of {self.document_type}",
        )

    def post(self, document: Any, *, allow_draft: bool = False) -> Any:
        if getattr(document, "status", None) == DocumentStatus.POSTED.value:
            raise BusinessRuleError("Document is already posted")
        if not allow_draft and document.status not in {
            DocumentStatus.APPROVED.value,
            DocumentStatus.DRAFT.value,
            DocumentStatus.PARTIALLY_FULFILLED.value,
        }:
            raise BusinessRuleError("Only approved documents can be posted")
        self.validate_posting(document)

        inventory_result = self.apply_inventory(document)
        lines = self.build_journal_lines(document, inventory_result)
        entry = None
        if lines:
            context = self._posting_context(document)
            entry = self.posting.build_entry(
                context=context, lines=lines, entry_type=self.document_type, auto_post=True, user_id=self.user_id
            )
            if hasattr(document, "journal_entry_id"):
                document.journal_entry_id = entry.id
        self.after_post(document, inventory_result, entry)
        self.transition(document, DocumentStatus.POSTED.value)
        self.db.flush()
        return document

    def unpost(self, document: Any, *, reason: str = "Correction") -> Any:
        if getattr(document, "status", None) != DocumentStatus.POSTED.value:
            raise BusinessRuleError("Only posted documents can be unposted")
        entry = None
        if getattr(document, "journal_entry_id", None):
            entry = self.db.get(JournalEntry, document.journal_entry_id)
        self._undo_posting(document, entry, reason=reason)
        self.after_unpost(document, entry)
        self.transition(document, DocumentStatus.DRAFT.value, reason=reason, action=AuditAction.UNPOST)
        return document

    def cancel(self, document: Any, *, reason: str) -> Any:
        if getattr(document, "status", None) == DocumentStatus.POSTED.value:
            # Cancelling a posted document must undo its stock and ledger effects
            # first: a cancelled document may never leave accounting or stock behind.
            entry = None
            if getattr(document, "journal_entry_id", None):
                entry = self.db.get(JournalEntry, document.journal_entry_id)
            self._undo_posting(document, entry, reason=f"Cancelled: {reason}")
            self.after_unpost(document, entry)
        return self.transition(document, DocumentStatus.CANCELLED.value, reason=reason, action=AuditAction.CANCEL)

    def _undo_posting(self, document: Any, entry: Any, *, reason: str) -> None:
        """Reverse the GL entry and the stock movements created at posting time."""
        if entry is not None and entry.status == DocumentStatus.POSTED.value:
            self.posting.reverse_entry(entry, reason=reason, user_id=self.user_id)
        self.reverse_inventory(document, entry)
        if hasattr(document, "journal_entry_id"):
            document.journal_entry_id = None

    def submit(self, document: Any) -> Any:
        return self.transition(document, DocumentStatus.SUBMITTED.value, action=AuditAction.SUBMIT)

    def approve(self, document: Any) -> Any:
        return self.transition(document, DocumentStatus.APPROVED.value, action=AuditAction.APPROVE)

    def reject(self, document: Any, *, reason: str) -> Any:
        return self.transition(document, DocumentStatus.REJECTED.value, reason=reason, action=AuditAction.REJECT)

    def _posting_context(self, document: Any):
        from app.services.posting_service import DocumentPostingContext

        return DocumentPostingContext(
            document_type=self.document_type,
            document_id=document.id,
            document_no=document.document_no,
            document_date=getattr(document, "document_date", None)
            or getattr(document, "entry_date", None)
            or getattr(document, "run_date", None)
            or getattr(document, "claim_date", None)
            or date.today(),
            description=getattr(document, "description", None)
            or f"{self.document_type.replace('_', ' ').title()} {document.document_no}",
            branch_id=getattr(document, "branch_id", None),
            currency_code=getattr(document, "currency_code", None),
            exchange_rate=Decimal(getattr(document, "exchange_rate", 1) or 1),
        )

    # -------------------------------------------------------------- helpers
    def apply_line_rows(self, document: Any, rows: Iterable[dict[str, Any]], *, replace: bool = True) -> None:
        """Create/refresh ORM line objects on ``document``."""
        if self.line_model is None:
            raise NotImplementedError("This service does not manage document lines")
        collection = getattr(document, self.line_relationship)
        if replace:
            collection.clear()
            self.db.flush()
        allowed = {column.key for column in self.line_model.__mapper__.columns}
        for row in rows:
            payload = {key: value for key, value in row.items() if key in allowed and key not in {"id", "created_at", "updated_at"}}
            # JSON payloads carry UUIDs as strings: coerce at the model boundary.
            for key, value in list(payload.items()):
                if isinstance(value, str) and key.endswith("_id"):
                    payload[key] = as_uuid(value)
                elif isinstance(value, (int, float, str)) and key.startswith(("quantity", "unit_price", "unit_cost")):
                    payload[key] = as_decimal(value)
            payload["company_id"] = self.company_id
            collection.append(self.line_model(**payload))
        self.db.flush()

    def permission_denied(self, action: str) -> None:
        raise PermissionDeniedError(f"You do not have permission to {action} {self.permission_entity}")


_ACTION_FOR_STATUS = {
    DocumentStatus.SUBMITTED.value: AuditAction.SUBMIT,
    DocumentStatus.APPROVED.value: AuditAction.APPROVE,
    DocumentStatus.REJECTED.value: AuditAction.REJECT,
    DocumentStatus.POSTED.value: AuditAction.POST,
    DocumentStatus.CANCELLED.value: AuditAction.CANCEL,
}
