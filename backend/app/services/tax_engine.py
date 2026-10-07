"""Configurable tax engine.

No country specific rule is hardcoded: taxes are rows with a type, a
computation (percentage / fixed amount), an inclusion mode (inclusive /
exclusive) and optional compound behaviour.  The engine turns a taxable base
into a breakdown that documents and postings consume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.enums import TaxComputation, TaxInclusion, TaxType
from app.core.errors import BusinessRuleError, NotFoundError
from app.models.masterdata import Product
from app.models.platform import Tax

TWO_PLACES = Decimal("0.01")


def money(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class TaxLineResult:
    tax_id: uuid.UUID | None
    code: str | None
    name: str | None
    tax_type: str
    rate: Decimal
    taxable_base: Decimal
    amount: Decimal
    is_inclusive: bool
    account_id: uuid.UUID | None = None

    def as_dict(self) -> dict:
        return {
            "tax_id": str(self.tax_id) if self.tax_id else None,
            "code": self.code,
            "name": self.name,
            "tax_type": self.tax_type,
            "rate": str(self.rate),
            "taxable_base": str(self.taxable_base),
            "amount": str(self.amount),
            "is_inclusive": self.is_inclusive,
            "account_id": str(self.account_id) if self.account_id else None,
        }


@dataclass(slots=True)
class TaxBreakdown:
    """Result of applying one or more taxes to a line or document."""

    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    lines: list[TaxLineResult] = field(default_factory=list)

    @property
    def tax_by_type(self) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for line in self.lines:
            totals[line.tax_type] = money(totals.get(line.tax_type, Decimal("0")) + line.amount)
        return totals


class TaxEngine:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id
        self._cache: dict[uuid.UUID, Tax | None] = {}

    # ----------------------------------------------------------------- lookup
    def get_tax(self, tax_id: uuid.UUID | None) -> Tax | None:
        if tax_id is None:
            return None
        if tax_id in self._cache:
            return self._cache[tax_id]
        tax = self.db.execute(
            select(Tax).where(Tax.company_id == self.company_id, Tax.id == tax_id)
        ).scalars().first()
        self._cache[tax_id] = tax
        return tax

    def require_tax(self, tax_id: uuid.UUID) -> Tax:
        tax = self.get_tax(tax_id)
        if tax is None:
            raise NotFoundError("Tax not found", tax_id=str(tax_id))
        return tax

    def tax_for_product(self, product: Product | None, *, purchase: bool = False) -> Tax | None:
        if product is None or product.tax_exempt:
            return None
        return self.get_tax(product.purchase_tax_id if purchase else product.sales_tax_id)

    def active_taxes(self, *, tax_type: str | None = None, on_date: date | None = None) -> list[Tax]:
        stmt = select(Tax).where(Tax.company_id == self.company_id, Tax.is_active.is_(True))
        if tax_type:
            stmt = stmt.where(Tax.tax_type == tax_type)
        if on_date:
            stmt = stmt.where(
                or_(Tax.effective_from.is_(None), Tax.effective_from <= on_date),
                or_(Tax.effective_to.is_(None), Tax.effective_to >= on_date),
            )
        return list(self.db.execute(stmt.order_by(Tax.code)).scalars().all())

    # -------------------------------------------------------------- computing
    def compute_tax_amount(self, base: Decimal, tax: Tax, *, previous_taxes: Decimal = Decimal("0")) -> Decimal:
        """Amount of a single tax applied to ``base``."""
        taxable = Decimal(base)
        if tax.is_compound:
            taxable = taxable + previous_taxes
        if tax.computation == TaxComputation.FIXED.value:
            return money(Decimal(tax.fixed_amount or 0))
        if tax.inclusion == TaxInclusion.INCLUSIVE.value and tax.rate:
            rate = Decimal(tax.rate) / Decimal("100")
            if rate >= 1:
                raise BusinessRuleError("Inclusive tax rate must be lower than 100%")
            return money(taxable - (taxable / (Decimal("1") + rate)))
        return money(taxable * Decimal(tax.rate or 0) / Decimal("100"))

    def net_from_inclusive(self, gross: Decimal, tax: Tax) -> Decimal:
        rate = Decimal(tax.rate or 0) / Decimal("100")
        if tax.inclusion == TaxInclusion.INCLUSIVE.value and rate > 0:
            return money(Decimal(gross) / (Decimal("1") + rate))
        return money(gross)

    def apply(
        self,
        amount: Decimal,
        *,
        tax: Tax | None = None,
        taxes: list[Tax] | None = None,
        prices_include_tax: bool = False,
    ) -> TaxBreakdown:
        """Apply one or several taxes to ``amount``.

        ``prices_include_tax`` (document level) overrides the tax definition's
        inclusion mode, which is what most ERPs offer for retail scenarios.
        """
        applied = taxes if taxes is not None else ([tax] if tax else [])
        applied = [item for item in applied if item is not None]
        if not applied:
            return TaxBreakdown(net_amount=money(amount), tax_amount=Decimal("0.00"), gross_amount=money(amount))

        # Inclusive prices: strip the tax out of the given amount.
        first_inclusive = prices_include_tax or any(item.inclusion == TaxInclusion.INCLUSIVE.value for item in applied)
        net = money(amount)
        results: list[TaxLineResult] = []
        accumulated = Decimal("0")
        if first_inclusive:
            total_rate = sum(
                (Decimal(item.rate or 0) for item in applied if item.inclusion == TaxInclusion.INCLUSIVE.value),
                Decimal("0"),
            ) / Decimal("100")
            if total_rate >= 1:
                raise BusinessRuleError("Total inclusive tax rate must be lower than 100%")
            net = money(Decimal(amount) / (Decimal("1") + total_rate))
        for item in applied:
            amount_tax = self.compute_tax_amount(net, item, previous_taxes=accumulated)
            results.append(
                TaxLineResult(
                    tax_id=item.id,
                    code=item.code,
                    name=item.name,
                    tax_type=item.tax_type,
                    rate=Decimal(item.rate or 0),
                    taxable_base=net,
                    amount=amount_tax,
                    is_inclusive=item.inclusion == TaxInclusion.INCLUSIVE.value or prices_include_tax,
                    account_id=item.sales_account_id if item.tax_type == TaxType.SALES.value else item.purchase_account_id,
                )
            )
            accumulated += amount_tax
        total_tax = money(accumulated)
        return TaxBreakdown(net_amount=net, tax_amount=total_tax, gross_amount=money(net + total_tax), lines=results)

    def apply_many(
        self, amount: Decimal, tax_ids: list[uuid.UUID], *, prices_include_tax: bool = False
    ) -> TaxBreakdown:
        taxes = [self.require_tax(tax_id) for tax_id in tax_ids if tax_id]
        return self.apply(amount, taxes=taxes, prices_include_tax=prices_include_tax)

    def withholding_amount(self, amount: Decimal, tax: Tax | None) -> Decimal:
        if tax is None:
            return Decimal("0.00")
        return self.compute_tax_amount(amount, tax)
