"""Row handlers used by :class:`ImportExportService` when committing an import."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.coercion import as_bool, as_decimal, as_uuid
from app.models.masterdata import Customer, Product, Supplier
from app.services.numbering_service import NumberingService


def _int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(Decimal(str(value)))


def _bool(value: Any, default: bool = True) -> bool:
    parsed = as_bool(value)
    return default if parsed is None else parsed


def _dec(value: Any) -> Decimal:
    return as_decimal(value) or Decimal("0")


def import_customer(importer: Any, data: dict[str, Any]) -> Customer:
    db = importer.db
    company_id = importer.company_id
    code = data.get("code") or NumberingService(db, company_id).next_number("customer")
    customer = Customer(
        company_id=company_id,
        code=code,
        name=data["name"],
        name_ar=data.get("name_ar"),
        email=data.get("email"),
        phone=data.get("phone"),
        mobile=data.get("mobile"),
        tax_registration_number=data.get("tax_registration_number"),
        country_code=data.get("country_code"),
        city=data.get("city"),
        address_line1=data.get("address_line1"),
        contact_person=data.get("contact_person"),
        credit_limit=_dec(data.get("credit_limit")),
        credit_days=_int(data.get("credit_days")),
        customer_group_id=as_uuid(data.get("group_code")),
        is_active=_bool(data.get("is_active")),
    )
    db.add(customer)
    db.flush()
    importer.audit.log_create(customer, entity_type="customer", label=customer.code)
    return customer


def import_supplier(importer: Any, data: dict[str, Any]) -> Supplier:
    db = importer.db
    company_id = importer.company_id
    code = data.get("code") or NumberingService(db, company_id).next_number("supplier")
    supplier = Supplier(
        company_id=company_id,
        code=code,
        name=data["name"],
        name_ar=data.get("name_ar"),
        email=data.get("email"),
        phone=data.get("phone"),
        mobile=data.get("mobile"),
        tax_registration_number=data.get("tax_registration_number"),
        country_code=data.get("country_code"),
        city=data.get("city"),
        address_line1=data.get("address_line1"),
        credit_limit=_dec(data.get("credit_limit")),
        credit_days=_int(data.get("credit_days")),
        lead_time_days=int(data.get("lead_time_days") or 0) or None,
        supplier_group_id=as_uuid(data.get("group_code")),
        is_active=_bool(data.get("is_active")),
    )
    db.add(supplier)
    db.flush()
    importer.audit.log_create(supplier, entity_type="supplier", label=supplier.code)
    return supplier


def import_product(importer: Any, data: dict[str, Any]) -> Product:
    db = importer.db
    product = Product(
        company_id=importer.company_id,
        sku=str(data["sku"]).strip().upper(),
        barcode=data.get("barcode"),
        name=data["name"],
        name_ar=data.get("name_ar"),
        description=data.get("description"),
        product_type=str(data.get("product_type") or "stock").lower(),
        category_id=as_uuid(data.get("category_code")),
        unit_id=as_uuid(data.get("unit_code")),
        purchase_price=_dec(data.get("purchase_price")),
        sales_price=_dec(data.get("sales_price")),
        cost_price=_dec(data.get("cost_price")) or _dec(data.get("purchase_price")),
        min_stock=_dec(data.get("min_stock")),
        max_stock=_dec(data.get("max_stock")),
        reorder_level=_dec(data.get("reorder_level")),
        reorder_quantity=_dec(data.get("reorder_quantity")),
        lead_time_days=_int(data.get("lead_time_days")),
        shelf_life_days=_int(data.get("shelf_life_days")) or None,
        track_inventory=str(data.get("product_type") or "stock").lower()
        not in {"service", "consumable"},
        is_sellable=_bool(data.get("is_sellable")),
        is_purchasable=_bool(data.get("is_purchasable")),
        is_active=_bool(data.get("is_active")),
    )
    db.add(product)
    db.flush()
    importer.audit.log_create(product, entity_type="product", label=product.sku)
    return product


IMPORT_HANDLERS = {
    "customer": import_customer,
    "supplier": import_supplier,
    "product": import_product,
}

__all__ = ["IMPORT_HANDLERS", "import_customer", "import_product", "import_supplier"]
