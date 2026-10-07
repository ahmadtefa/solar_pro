"""Platform level models: tenancy hierarchy, geography, currency, tax,
units of measure, numbering, fiscal calendar, settings and module activation."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AddressType,
    CurrencyRateType,
    ModuleKey,
    TaxComputation,
    TaxInclusion,
    TaxType,
)
from app.models.base import (
    Base,
    CompanyScoped,
    JSONType,
    Money,
    Percent,
    Quantity,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Company(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A tenant.  Every business row in the system belongs to exactly one company."""

    __tablename__ = "companies"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(250))
    tax_registration_number: Mapped[str | None] = mapped_column(String(64))
    commercial_registry: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(64))
    base_currency_code: Mapped[str] = mapped_column(String(3), default="EGP", nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Cairo", nullable=False)
    default_language: Mapped[str] = mapped_column(String(5), default="ar", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(160))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    valuation_method: Mapped[str] = mapped_column(String(16), default="average", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_parent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL")
    )
    settings_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    branches: Mapped[list[Branch]] = relationship(back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("fiscal_year_start_month BETWEEN 1 AND 12", name="fiscal_month_valid"),
        Index("ix_companies_active", "is_active"),
    )


class Branch(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "branches"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    is_head_office: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    city_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"))
    country_code: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    company: Mapped[Company] = relationship(back_populates="branches")

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_branches_company_code"),
        Index("ix_branches_company_active", "company_id", "is_active"),
    )


class Department(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "departments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_departments_company_code"),
        Index("ix_departments_company_active", "company_id", "is_active"),
    )


class Division(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Commercial or operational division inside a company (e.g. Solar, Trading)."""

    __tablename__ = "divisions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL")
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_divisions_company_code"),)


class CostCenter(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "cost_centers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cost_centers.id", ondelete="SET NULL")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_cost_centers_company_code"),)


class Country(Base, UUIDMixin, TimestampMixin):
    """Global reference data (not tenant scoped)."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    phone_code: Mapped[str | None] = mapped_column(String(8))
    default_currency_code: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class City(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "cities"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    code: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_cities_company_country", "company_id", "country_code"),)


class Address(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Reusable address, attachable to any party type."""

    __tablename__ = "addresses"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_type: Mapped[str] = mapped_column(String(24), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    address_type: Mapped[str] = mapped_column(String(16), default=AddressType.OTHER.value, nullable=False)
    label: Mapped[str | None] = mapped_column(String(80))
    address_line1: Mapped[str] = mapped_column(String(250), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    latitude: Mapped[Decimal | None] = mapped_column(Rate)
    longitude: Mapped[Decimal | None] = mapped_column(Rate)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_addresses_party", "company_id", "party_type", "party_id"),)


class Currency(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(80))
    symbol: Mapped[str | None] = mapped_column(String(8))
    decimal_places: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ExchangeRate(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "exchange_rates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    base_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    rate_type: Mapped[str] = mapped_column(String(16), default=CurrencyRateType.SPOT.value, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("rate > 0", name="rate_positive"),
        Index("ix_exchange_rates_lookup", "company_id", "currency_code", "effective_from"),
    )


class Tax(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Configurable tax definition - no country specific logic is hardcoded."""

    __tablename__ = "taxes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    tax_type: Mapped[str] = mapped_column(String(24), default=TaxType.SALES.value, nullable=False)
    computation: Mapped[str] = mapped_column(String(16), default=TaxComputation.PERCENTAGE.value, nullable=False)
    inclusion: Mapped[str] = mapped_column(String(16), default=TaxInclusion.EXCLUSIVE.value, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    fixed_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_compound: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applies_to_all_items: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sales_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    purchase_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    withholding_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_taxes_company_code"),
        CheckConstraint("rate >= 0", name="rate_non_negative"),
    )


class PaymentTerm(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "payment_terms"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_days: Mapped[int | None] = mapped_column(Integer)
    discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_payment_terms_company_code"),)


class UnitGroup(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Group of interchangeable units (e.g. weight, volume, packaging)."""

    __tablename__ = "unit_groups"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120))
    base_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_unit_groups_company_code"),)


class UnitOfMeasure(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "units_of_measure"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(80))
    symbol: Mapped[str | None] = mapped_column(String(16))
    unit_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("unit_groups.id", ondelete="SET NULL")
    )
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_fraction: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_units_company_code"),)


class UnitConversion(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Conversion factor between two units (1 carton = 24 pieces)."""

    __tablename__ = "unit_conversions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_unit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("units_of_measure.id", ondelete="CASCADE"), nullable=False
    )
    to_unit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("units_of_measure.id", ondelete="CASCADE"), nullable=False
    )
    factor: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "from_unit_id", "to_unit_id", name="uq_unit_conversions_pair"),
        CheckConstraint("factor > 0", name="factor_positive"),
    )


class NumberSequence(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Server side document numbering - gapless per company/document type."""

    __tablename__ = "number_sequences"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE")
    )
    prefix: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    suffix: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    padding: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reset_yearly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_year: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", "branch_id", name="uq_number_sequences_scope"),
        CheckConstraint("next_number > 0", name="next_number_positive"),
    )


class DocumentType(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Registry describing every document the platform understands."""

    __tablename__ = "document_types"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    module: Mapped[str] = mapped_column(String(48), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    affects_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    affects_accounting: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_document_types_company_code"),)


class FiscalYear(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "fiscal_years"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    periods: Mapped[list[FiscalPeriod]] = relationship(
        back_populates="fiscal_year", cascade="all, delete-orphan", order_by="FiscalPeriod.period_number"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_fiscal_years_company_code"),
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
    )


class FiscalPeriod(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "fiscal_periods"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fiscal_year: Mapped[FiscalYear] = relationship(back_populates="periods")

    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "period_number", name="uq_fiscal_periods_number"),
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
    )


class SystemSetting(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Key/value configuration, optionally scoped to a user."""

    __tablename__ = "system_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict | list | None] = mapped_column(JSONType)
    category: Mapped[str] = mapped_column(String(48), default="general", nullable=False)
    scope: Mapped[str] = mapped_column(String(24), default="company", nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "key", "scope", "user_id", name="uq_system_settings_key_scope"),
    )


class ModuleActivation(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Which modules are switched on for a company (extensibility hook)."""

    __tablename__ = "module_activations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_key: Mapped[str] = mapped_column(String(48), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "module_key", name="uq_module_activations_key"),)


class KitItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Component lines for KIT / BUNDLE products."""

    __tablename__ = "kit_items"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kit_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    component_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_kit_items_kit", "kit_product_id"),)


DEFAULT_MODULES: tuple[str, ...] = tuple(module.value for module in ModuleKey)
