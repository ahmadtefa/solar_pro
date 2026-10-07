"""Master data, document action and reporting schemas.

Master data payloads allow extra keys: the service layer owns validation, and the
extra fields are forwarded to the model attributes it understands.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class FlexiblePayload(BaseModel):
    """Base payload: known fields are typed, unknown fields pass through."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    def data(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)


# --------------------------------------------------------------------------- #
# Organisation
# --------------------------------------------------------------------------- #
class CompanyCreate(FlexiblePayload):
    code: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., min_length=2, max_length=200)
    name_ar: str | None = None
    legal_name: str | None = None
    base_currency_code: str = Field("USD", min_length=3, max_length=3)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    timezone: str | None = None
    default_language: Literal["ar", "en"] = "ar"
    industry: str | None = None
    fiscal_year_start_month: int = Field(1, ge=1, le=12)
    valuation_method: Literal["fifo", "average", "standard"] = "average"
    admin_email: EmailStr | None = None
    admin_password: str | None = Field(None, min_length=8, max_length=128)
    admin_full_name: str | None = None
    taxes: list[dict[str, Any]] = Field(default_factory=list)


class CompanyUpdate(FlexiblePayload):
    name: str | None = None
    name_ar: str | None = None
    legal_name: str | None = None
    tax_registration_number: str | None = None
    commercial_registry: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    logo_url: str | None = None
    is_active: bool | None = None


class BranchCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=160)
    name_ar: str | None = None
    city_id: uuid.UUID | None = None
    country_code: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    is_head_office: bool = False
    manager_id: uuid.UUID | None = None


class DepartmentCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=160)
    name_ar: str | None = None
    branch_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


class CostCenterCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=160)
    name_ar: str | None = None
    parent_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None


class CurrencyCreate(FlexiblePayload):
    code: str = Field(..., min_length=3, max_length=3)
    name: str = Field(..., min_length=2, max_length=80)
    name_ar: str | None = None
    symbol: str | None = None
    decimal_places: int = Field(2, ge=0, le=6)
    is_active: bool = True


class ExchangeRateCreate(FlexiblePayload):
    currency_code: str = Field(..., min_length=3, max_length=3)
    base_currency_code: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0)
    rate_type: str = "spot"
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True


class TaxCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=120)
    name_ar: str | None = None
    tax_type: Literal["sales", "purchase", "withholding", "both"] = "sales"
    computation: Literal["percentage", "fixed"] = "percentage"
    inclusion: Literal["exclusive", "inclusive"] = "exclusive"
    rate: Decimal = Field(Decimal("0"), ge=0, le=100)
    fixed_amount: Decimal = Decimal("0")
    is_compound: bool = False
    applies_to_all_items: bool = True
    recoverable: bool = True
    effective_from: date | None = None
    effective_to: date | None = None


class PaymentTermCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=120)
    name_ar: str | None = None
    days: int = Field(0, ge=0, le=3650)
    discount_days: int | None = Field(None, ge=0, le=3650)
    discount_percent: Decimal | None = Field(None, ge=0, le=100)


class UnitCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=16)
    name: str = Field(..., min_length=1, max_length=80)
    name_ar: str | None = None
    symbol: str | None = None
    unit_group_id: uuid.UUID | None = None
    allow_fraction: bool = True


class FiscalYearCreate(FlexiblePayload):
    code: str = Field(..., min_length=4, max_length=16)
    name: str | None = None
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def _ordered(cls, value: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("end_date must be after start_date")
        return value


class SettingUpdate(FlexiblePayload):
    key: str = Field(..., min_length=2, max_length=120)
    value: Any = None
    category: str | None = None
    scope: str = "company"


# --------------------------------------------------------------------------- #
# Parties and items
# --------------------------------------------------------------------------- #
class CustomerCreate(FlexiblePayload):
    code: str | None = Field(None, max_length=32)
    name: str = Field(..., min_length=2, max_length=200)
    name_ar: str | None = None
    customer_group_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    salesperson_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    tax_registration_number: str | None = None
    country_code: str | None = None
    city: str | None = None
    address_line1: str | None = None
    contact_person: str | None = None
    credit_limit: Decimal = Field(Decimal("0"), ge=0)
    credit_days: int = Field(0, ge=0, le=3650)
    payment_term_id: uuid.UUID | None = None
    price_list_id: uuid.UUID | None = None
    currency_code: str | None = None
    notes: str | None = None


class SupplierCreate(FlexiblePayload):
    code: str | None = Field(None, max_length=32)
    name: str = Field(..., min_length=2, max_length=200)
    name_ar: str | None = None
    supplier_group_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    buyer_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    tax_registration_number: str | None = None
    country_code: str | None = None
    city: str | None = None
    address_line1: str | None = None
    contact_person: str | None = None
    credit_limit: Decimal = Field(Decimal("0"), ge=0)
    credit_days: int = Field(0, ge=0, le=3650)
    payment_term_id: uuid.UUID | None = None
    currency_code: str | None = None
    lead_time_days: int | None = None
    withholding_tax_id: uuid.UUID | None = None
    notes: str | None = None


class ProductCreate(FlexiblePayload):
    sku: str | None = Field(None, max_length=64)
    barcode: str | None = None
    name: str = Field(..., min_length=1, max_length=200)
    name_ar: str | None = None
    description: str | None = None
    product_type: Literal["stock", "service", "consumable", "asset", "kit", "bundle"] = "stock"
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    purchase_price: Decimal = Field(Decimal("0"), ge=0)
    sales_price: Decimal = Field(Decimal("0"), ge=0)
    cost_price: Decimal = Field(Decimal("0"), ge=0)
    min_sales_price: Decimal | None = None
    sales_tax_id: uuid.UUID | None = None
    purchase_tax_id: uuid.UUID | None = None
    tax_exempt: bool = False
    track_inventory: bool | None = None
    track_batches: bool = False
    track_serials: bool = False
    track_expiry: bool = False
    allow_negative_stock: bool = False
    min_stock: Decimal = Decimal("0")
    max_stock: Decimal = Decimal("0")
    reorder_level: Decimal = Decimal("0")
    reorder_quantity: Decimal = Decimal("0")
    lead_time_days: int = 0
    shelf_life_days: int | None = None
    valuation_method: Literal["fifo", "average", "standard"] | None = None
    inventory_account_id: uuid.UUID | None = None
    sales_account_id: uuid.UUID | None = None
    cogs_account_id: uuid.UUID | None = None
    is_sellable: bool = True
    is_purchasable: bool = True
    is_manufactured: bool = False
    default_warehouse_id: uuid.UUID | None = None
    preferred_supplier_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)


class WarehouseCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=2, max_length=160)
    name_ar: str | None = None
    branch_id: uuid.UUID | None = None
    address: str | None = None
    city: str | None = None
    country_code: str | None = None
    manager_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    inventory_account_id: uuid.UUID | None = None
    allows_negative_stock: bool = False
    is_transit: bool = False
    is_quarantine: bool = False


class AccountCreate(FlexiblePayload):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=160)
    name_ar: str | None = None
    account_type: Literal["asset", "liability", "equity", "revenue", "expense"]
    parent_id: uuid.UUID | None = None
    is_group: bool = False
    is_postable: bool = True
    currency_code: str | None = None
    requires_cost_center: bool = False
    requires_party: bool = False
    is_cash_account: bool = False
    is_bank_account: bool = False
    opening_balance: Decimal | None = None
    opening_balance_date: date | None = None


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
class DocumentLinePayload(FlexiblePayload):
    product_id: uuid.UUID | None = None
    description: str | None = None
    unit_id: uuid.UUID | None = None
    quantity: Decimal = Field(Decimal("1"), gt=0)
    unit_price: Decimal = Field(Decimal("0"), ge=0)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    discount_amount: Decimal | None = None
    tax_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    notes: str | None = None


class SalesDocumentCreate(FlexiblePayload):
    customer_id: uuid.UUID
    document_date: date | None = None
    due_date: date | None = None
    delivery_date: date | None = None
    branch_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    currency_code: str | None = None
    payment_term_id: uuid.UUID | None = None
    salesperson_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    price_list_id: uuid.UUID | None = None
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    discount_amount: Decimal = Field(Decimal("0"), ge=0)
    other_charges: Decimal = Decimal("0")
    shipping_amount: Decimal = Decimal("0")
    notes: str | None = None
    reference: str | None = None
    lines: list[DocumentLinePayload] = Field(default_factory=list)


class PurchaseDocumentCreate(FlexiblePayload):
    supplier_id: uuid.UUID
    document_date: date | None = None
    due_date: date | None = None
    branch_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    currency_code: str | None = None
    payment_term_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    discount_amount: Decimal = Field(Decimal("0"), ge=0)
    other_charges: Decimal = Decimal("0")
    shipping_amount: Decimal = Decimal("0")
    notes: str | None = None
    reference: str | None = None
    lines: list[DocumentLinePayload] = Field(default_factory=list)


class PaymentCreate(FlexiblePayload):
    party_type: Literal["customer", "supplier", "employee", "other"] = "customer"
    party_id: uuid.UUID | None = None
    direction: Literal["inbound", "outbound"]
    amount: Decimal = Field(..., gt=0)
    payment_method: Literal["cash", "bank_transfer", "cheque", "card", "wallet", "other"] = "cash"
    cash_account_id: uuid.UUID | None = None
    bank_account_id: uuid.UUID | None = None
    payment_account_id: uuid.UUID | None = None
    document_date: date | None = None
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    withholding_amount: Decimal = Decimal("0")
    reference: str | None = None
    notes: str | None = None
    branch_id: uuid.UUID | None = None
    allocations: list[dict[str, Any]] = Field(default_factory=list)


class JournalEntryCreate(FlexiblePayload):
    entry_date: date
    description: str = Field(..., min_length=2, max_length=400)
    entry_type: str = "manual"
    reference: str | None = None
    branch_id: uuid.UUID | None = None
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    lines: list[dict[str, Any]] = Field(default_factory=list)
    auto_post: bool = True


class StockAdjustmentCreate(FlexiblePayload):
    warehouse_id: uuid.UUID
    document_date: date | None = None
    reason: str = Field(..., min_length=3, max_length=400)
    lines: list[DocumentLinePayload] = Field(default_factory=list)


class StockTransferCreate(FlexiblePayload):
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    document_date: date | None = None
    notes: str | None = None
    lines: list[DocumentLinePayload] = Field(default_factory=list)


class ReportRunRequest(FlexiblePayload):
    params: dict[str, Any] = Field(default_factory=dict)
    file_format: Literal["json", "csv", "xlsx", "pdf"] = "json"


class DashboardRequest(FlexiblePayload):
    date_from: date | None = None
    date_to: date | None = None
    branch_id: uuid.UUID | None = None


class ImportCommitRequest(FlexiblePayload):
    skip_invalid: bool = True


class SearchRequest(FlexiblePayload):
    query: str = Field(..., min_length=2, max_length=120)
    entities: list[str] | None = None
    limit_per_entity: int = Field(5, ge=1, le=25)


class NotificationCreate(FlexiblePayload):
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    title: str = Field(..., min_length=2, max_length=200)
    body: str | None = None
    notification_type: str = "info"
    module: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action_url: str | None = None


class AttachmentMeta(FlexiblePayload):
    entity_type: str = Field(..., min_length=2, max_length=64)
    entity_id: uuid.UUID
    title: str | None = None
    description: str | None = None
    category: str | None = None
    is_public: bool = False


class WorkflowActionRequest(FlexiblePayload):
    action: Literal["approve", "reject", "cancel", "delegate", "comment"]
    remarks: str | None = None
    delegate_to_id: uuid.UUID | None = None


class TimelineEvent(BaseModel):
    at: datetime
    kind: str
    title: str
    detail: str | None = None
    actor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AccountCreate",
    "AttachmentMeta",
    "BranchCreate",
    "CompanyCreate",
    "CompanyUpdate",
    "CostCenterCreate",
    "CurrencyCreate",
    "CustomerCreate",
    "DashboardRequest",
    "DepartmentCreate",
    "DocumentLinePayload",
    "ExchangeRateCreate",
    "FiscalYearCreate",
    "FlexiblePayload",
    "ImportCommitRequest",
    "JournalEntryCreate",
    "NotificationCreate",
    "PaymentCreate",
    "PaymentTermCreate",
    "ProductCreate",
    "PurchaseDocumentCreate",
    "ReportRunRequest",
    "SalesDocumentCreate",
    "SearchRequest",
    "SettingUpdate",
    "StockAdjustmentCreate",
    "StockTransferCreate",
    "SupplierCreate",
    "TaxCreate",
    "TimelineEvent",
    "UnitCreate",
    "WarehouseCreate",
    "WorkflowActionRequest",
]
