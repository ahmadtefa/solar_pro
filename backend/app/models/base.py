"""Shared column types and mixins for the ORM models."""

from __future__ import annotations

import uuid
from decimal import Decimal  # noqa: F401 - re-exported for models

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import (  # noqa: F401  (re-exported for models)
    AuditFieldsMixin,
    Base,
    CompanyScoped,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)

#: JSON column that uses the native JSONB type on PostgreSQL.  Values stored in
#: metadata payloads must already be JSON safe - use app.core.jsonutil.json_safe.
JSONType = JSON().with_variant(JSONB, "postgresql")

#: Monetary amounts - 4 decimals keeps unit prices and FX rates accurate.
Money = Numeric(18, 4)
#: Quantities - fractional units (kg, metres) are supported.
Quantity = Numeric(18, 4)
#: Exchange / conversion rates.
Rate = Numeric(18, 8)
#: Percentages.
Percent = Numeric(9, 4)


def company_fk() -> Mapped[uuid.UUID]:
    """Standard tenant column present on every company scoped table."""
    return mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)


def zero() -> Decimal:
    return Decimal("0")


__all__ = [
    "AuditFieldsMixin",
    "Base",
    "CheckConstraint",
    "CompanyScoped",
    "Index",
    "JSONType",
    "Money",
    "Percent",
    "Quantity",
    "Rate",
    "SoftDeleteMixin",
    "String",
    "TimestampMixin",
    "UUIDMixin",
    "company_fk",
    "zero",
]
