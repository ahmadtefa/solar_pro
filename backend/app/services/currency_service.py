"""Currency and exchange-rate service.

Owns every FX lookup so documents never re-implement rate resolution:
historical rates, latest rates, conversion between any two currencies of the
company and the reporting helpers used by the dashboards and reports.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, ValidationFailure
from app.models.platform import Company, Currency, ExchangeRate
from app.services.posting_service import money


class CurrencyService:
    """Historical-rate aware currency conversion for one company."""

    def __init__(self, db: Session, company_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.company_id = company_id

    # ------------------------------------------------------------------ lookup
    @property
    def base_currency(self) -> str:
        if self.company_id:
            company = self.db.get(Company, self.company_id)
            if company is not None and company.base_currency_code:
                return str(company.base_currency_code).upper()
        return "USD"

    def get_currency(self, code: str) -> Currency | None:
        return self.db.execute(
            select(Currency).where(Currency.code == (code or "").strip().upper())
        ).scalars().first()

    def require_currency(self, code: str) -> Currency:
        currency = self.get_currency(code)
        if currency is None:
            raise NotFoundError(f"Currency {code} is not configured", currency_code=code)
        return currency

    def rate(
        self,
        currency_code: str,
        *,
        company_id: uuid.UUID | None = None,
        on_date: date | None = None,
        base_currency_code: str | None = None,
    ) -> Decimal:
        """Rate of one foreign unit expressed in the company base currency."""
        company_id = company_id or self.company_id
        base = (base_currency_code or self.base_currency).upper()
        code = (currency_code or "").strip().upper()
        if not code or code == base:
            return Decimal("1")
        on_date = on_date or date.today()
        row = self.db.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.company_id == company_id,
                ExchangeRate.currency_code == code,
                ExchangeRate.base_currency_code == base,
                ExchangeRate.is_active.is_(True),
                ExchangeRate.effective_from <= on_date,
            )
            .order_by(ExchangeRate.effective_from.desc())
        ).scalars().first()
        if row is None:
            raise BusinessRuleError(
                f"No exchange rate for {code} on {on_date.isoformat()}",
                currency_code=code,
                base_currency_code=base,
            )
        if row.effective_to and row.effective_to < on_date:
            raise BusinessRuleError(
                f"The exchange rate for {code} expired on {row.effective_to.isoformat()}",
                currency_code=code,
            )
        return Decimal(row.rate)

    def convert(
        self,
        amount: Decimal | str | float,
        from_currency: str,
        to_currency: str,
        *,
        company_id: uuid.UUID | None = None,
        on_date: date | None = None,
    ) -> dict[str, Any]:
        """Convert ``amount`` between two currencies with historical rates."""
        source = Decimal(str(amount or 0))
        from_code = (from_currency or "").strip().upper()
        to_code = (to_currency or "").strip().upper()
        if not from_code or not to_code:
            raise ValidationFailure("Both currencies are required")
        if from_code == to_code:
            return {"amount": money(source), "rate": Decimal("1"), "currency_code": to_code}
        base = self.base_currency
        from_rate = self.rate(from_code, company_id=company_id, on_date=on_date, base_currency_code=base)
        to_rate = self.rate(to_code, company_id=company_id, on_date=on_date, base_currency_code=base)
        if to_rate == 0:
            raise ValidationFailure("Target exchange rate must not be zero")
        in_base = source * from_rate
        converted = in_base / to_rate
        return {
            "amount": money(converted),
            "rate": (from_rate / to_rate).quantize(Decimal("0.00000001")),
            "currency_code": to_code,
            "base_currency_code": base,
            "in_base_currency": money(in_base),
        }

    def to_base(
        self, amount: Decimal, currency_code: str | None, *, on_date: date | None = None
    ) -> tuple[Decimal, Decimal]:
        """Return ``(base_amount, rate)`` for an amount in a possibly foreign currency."""
        if not currency_code or currency_code.upper() == self.base_currency:
            return money(amount), Decimal("1")
        rate = self.rate(currency_code, on_date=on_date)
        return money(Decimal(amount) * rate), rate

    def from_base(
        self, amount: Decimal, currency_code: str | None, *, on_date: date | None = None
    ) -> tuple[Decimal, Decimal]:
        if not currency_code or currency_code.upper() == self.base_currency:
            return money(amount), Decimal("1")
        rate = self.rate(currency_code, on_date=on_date)
        if rate == 0:
            raise ValidationFailure("Exchange rate must not be zero")
        return money(Decimal(amount) / rate), rate

    # ------------------------------------------------------------------ config
    def latest_rates(self, *, company_id: uuid.UUID | None = None, base: str | None = None) -> list[dict[str, Any]]:
        company_id = company_id or self.company_id
        base_code = (base or self.base_currency).upper()
        rows = self.db.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.company_id == company_id,
                ExchangeRate.base_currency_code == base_code,
                ExchangeRate.is_active.is_(True),
            )
            .order_by(ExchangeRate.currency_code, ExchangeRate.effective_from.desc())
        ).scalars().all()
        seen: dict[str, ExchangeRate] = {}
        for row in rows:
            seen.setdefault(row.currency_code, row)
        return [
            {
                "currency_code": row.currency_code,
                "base_currency_code": row.base_currency_code,
                "rate": str(row.rate),
                "rate_type": row.rate_type,
                "effective_from": row.effective_from.isoformat(),
                "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            }
            for row in seen.values()
        ]

    def upsert_rate(
        self,
        *,
        currency_code: str,
        rate: Decimal | str,
        base_currency_code: str | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
        rate_type: str = "spot",
        company_id: uuid.UUID | None = None,
    ) -> ExchangeRate:
        company_id = company_id or self.company_id
        if company_id is None:
            raise ValidationFailure("A company is required to store an exchange rate")
        code = (currency_code or "").strip().upper()
        base = (base_currency_code or self.base_currency).upper()
        if code == base:
            raise ValidationFailure("A currency cannot be rated against itself")
        self.require_currency(base)
        self.require_currency(code)
        value = Decimal(str(rate))
        if value <= 0:
            raise ValidationFailure("The exchange rate must be greater than zero")
        start = effective_from or date.today()
        row = self.db.execute(
            select(ExchangeRate).where(
                ExchangeRate.company_id == company_id,
                ExchangeRate.currency_code == code,
                ExchangeRate.base_currency_code == base,
                ExchangeRate.effective_from == start,
                ExchangeRate.rate_type == rate_type,
            )
        ).scalars().first()
        if row is None:
            row = ExchangeRate(
                company_id=company_id,
                currency_code=code,
                base_currency_code=base,
                rate=value,
                rate_type=rate_type,
                effective_from=start,
                effective_to=effective_to,
                is_active=True,
            )
            self.db.add(row)
        else:
            row.rate = value
            row.effective_to = effective_to
            row.is_active = True
        self.db.flush()
        return row

    def codes_in_use(self, *, company_id: uuid.UUID | None = None) -> list[str]:
        """Every currency with a stored rate, plus the base currency."""
        company_id = company_id or self.company_id
        rows = self.db.execute(
            select(ExchangeRate.currency_code)
            .where(ExchangeRate.company_id == company_id)
            .group_by(ExchangeRate.currency_code)
        ).all()
        codes = {row[0] for row in rows if row[0]}
        codes.add(self.base_currency)
        return sorted(codes)


__all__ = ["CurrencyService"]
