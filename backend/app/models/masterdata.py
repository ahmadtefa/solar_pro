"""Master data: products, customers, suppliers, warehouses and pricing."""

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

from app.core.enums import PartyType, ProductType, ValuationMethod
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


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
class ProductCategory(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "product_categories"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_categories.id", ondelete="SET NULL")
    )
    path: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_product_categories_company_code"),)


class Brand(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "brands"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_brands_company_code"),)


class Product(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Universal item master: stock items, services, consumables, assets, kits."""

    __tablename__ = "products"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(String(16), default=ProductType.STOCK.value, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_categories.id", ondelete="SET NULL")
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    is_variant_parent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    variant_attributes: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    # pricing
    purchase_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    sales_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    min_sales_price: Mapped[Decimal | None] = mapped_column(Money)
    cost_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # tax
    sales_tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    purchase_tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))
    tax_exempt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # stock control
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    track_batches: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    track_serials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    track_expiry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_variants: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_stock: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    max_stock: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    reorder_level: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    reorder_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    valuation_method: Mapped[str] = mapped_column(String(16), default=ValuationMethod.AVERAGE.value, nullable=False)
    standard_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Quantity)
    volume: Mapped[Decimal | None] = mapped_column(Quantity)

    # accounting links (populated per company chart of accounts)
    inventory_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    sales_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    cogs_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    asset_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))

    currency_code: Mapped[str | None] = mapped_column(String(3))
    default_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL")
    )
    preferred_supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_sellable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_purchasable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_manufactured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    units: Mapped[list[ProductUnit]] = relationship(
        back_populates="product", cascade="all, delete-orphan", foreign_keys="ProductUnit.product_id"
    )
    barcodes: Mapped[list[ProductBarcode]] = relationship(back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_products_company_sku"),
        CheckConstraint("sales_price >= 0", name="sales_price_non_negative"),
        CheckConstraint("purchase_price >= 0", name="purchase_price_non_negative"),
        Index("ix_products_company_active", "company_id", "is_active"),
        Index("ix_products_company_name", "company_id", "name"),
    )


class ProductBarcode(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    __tablename__ = "product_barcodes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    label: Mapped[str | None] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[Product] = relationship(back_populates="barcodes")

    __table_args__ = (UniqueConstraint("company_id", "barcode", name="uq_product_barcodes_company_barcode"),)


class ProductUnit(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Product specific unit with its own price and conversion factor."""

    __tablename__ = "product_units"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=False
    )
    conversion_factor: Mapped[Decimal] = mapped_column(Rate, default=Decimal("1"), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    sales_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_base_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default_sales: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default_purchase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64))

    product: Mapped[Product] = relationship(back_populates="units", foreign_keys=[product_id])

    __table_args__ = (
        UniqueConstraint("product_id", "unit_id", name="uq_product_units_pair"),
        CheckConstraint("conversion_factor > 0", name="conversion_factor_positive"),
    )


class CustomerGroup(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "customer_groups"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    default_discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_customer_groups_company_code"),)


class SupplierGroup(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "supplier_groups"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_supplier_groups_company_code"),)


class Customer(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "customers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    customer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_groups.id", ondelete="SET NULL")
    )
    parent_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(40))
    mobile: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(200))
    tax_registration_number: Mapped[str | None] = mapped_column(String(64))
    commercial_registry: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    contact_person: Mapped[str | None] = mapped_column(String(160))

    # credit control
    credit_limit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    default_discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    is_credit_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credit_hold_reason: Mapped[str | None] = mapped_column(String(250))

    # accounting
    receivable_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    revenue_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    ledger_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", foreign_keys="Contact.customer_id"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_customers_company_code"),
        CheckConstraint("credit_limit >= 0", name="credit_limit_non_negative"),
        Index("ix_customers_company_name", "company_id", "name"),
        Index("ix_customers_company_active", "company_id", "is_active"),
    )


class Supplier(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "suppliers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    supplier_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_groups.id", ondelete="SET NULL")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(40))
    mobile: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(200))
    tax_registration_number: Mapped[str | None] = mapped_column(String(64))
    commercial_registry: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    contact_person: Mapped[str | None] = mapped_column(String(160))

    credit_limit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_terms.id"))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating: Mapped[Decimal | None] = mapped_column(Percent)
    withholding_tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("taxes.id"))

    payable_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    ledger_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    block_reason: Mapped[str | None] = mapped_column(String(250))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan", foreign_keys="Contact.supplier_id"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_suppliers_company_code"),
        Index("ix_suppliers_company_name", "company_id", "name"),
        Index("ix_suppliers_company_active", "company_id", "is_active"),
    )


class Contact(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Contact person for a customer, supplier or any other party."""

    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_type: Mapped[str] = mapped_column(String(24), default=PartyType.CUSTOMER.value, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE")
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE")
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(40))
    mobile: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship(back_populates="contacts", foreign_keys=[customer_id])
    supplier: Mapped[Supplier | None] = relationship(back_populates="contacts", foreign_keys=[supplier_id])

    __table_args__ = (
        Index("ix_contacts_customer", "customer_id"),
        Index("ix_contacts_supplier", "supplier_id"),
    )


class SupplierProduct(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Supplier catalogue entry with vendor specific price and lead time."""

    __tablename__ = "supplier_products"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(64))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    last_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    min_order_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    last_purchase_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", name="uq_supplier_products_pair"),
        Index("ix_supplier_products_product", "company_id", "product_id"),
    )


class SupplierPriceHistory(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Immutable price history used for supplier comparison and analytics."""

    __tablename__ = "supplier_price_history"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    source_document_type: Mapped[str | None] = mapped_column(String(48))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(250))

    __table_args__ = (Index("ix_supplier_price_history_lookup", "company_id", "product_id", "price_date"),)


# --------------------------------------------------------------------------- #
# Warehouses and storage locations
# --------------------------------------------------------------------------- #
class Warehouse(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "warehouses"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(160))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id"))
    address: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cost_centers.id"))
    inventory_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.id"))
    allows_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_transit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_quarantine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capacity_area: Mapped[Decimal | None] = mapped_column(Quantity)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    zones: Mapped[list[WarehouseZone]] = relationship(back_populates="warehouse", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_warehouses_company_code"),
        Index("ix_warehouses_company_active", "company_id", "is_active"),
    )


class WarehouseZone(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "warehouse_zones"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    zone_type: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    warehouse: Mapped[Warehouse] = relationship(back_populates="zones")
    locations: Mapped[list[WarehouseLocation]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_warehouse_zones_warehouse_code"),)


class WarehouseLocation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    """Bin / shelf / rack position inside a zone."""

    __tablename__ = "warehouse_locations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouse_zones.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    aisle: Mapped[str | None] = mapped_column(String(24))
    shelf: Mapped[str | None] = mapped_column(String(24))
    bin_number: Mapped[str | None] = mapped_column(String(24))
    barcode: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    zone: Mapped[WarehouseZone | None] = relationship(back_populates="locations")

    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_warehouse_locations_warehouse_code"),)


class PriceList(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "price_lists"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    applies_to: Mapped[str] = mapped_column(String(16), default=PartyType.CUSTOMER.value, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_price_lists_company_code"),)


class PriceListItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, CompanyScoped):
    __tablename__ = "price_list_items"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("units_of_measure.id"))
    min_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint(
            "price_list_id", "product_id", "unit_id", "min_quantity", name="uq_price_list_items_scope"
        ),
    )


class PartyStatusHistory(Base, UUIDMixin, TimestampMixin, CompanyScoped):
    """Generic timeline entry for customers / suppliers (credit hold, rating...)."""

    __tablename__ = "party_status_history"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_type: Mapped[str] = mapped_column(String(24), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(48))
    reason: Mapped[str | None] = mapped_column(String(250))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
