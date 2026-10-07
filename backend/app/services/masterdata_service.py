"""Master data: items, customers, suppliers and their satellites.

The API layer and the importers share these services so a product created by
hand and a product created from a spreadsheet go through exactly the same
validation, numbering and pricing rules.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.coercion import as_decimal, as_uuid
from app.core.enums import PartyType, ProductType
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, ValidationFailure
from app.models.masterdata import (
    Contact,
    Customer,
    CustomerGroup,
    PriceList,
    PriceListItem,
    Product,
    ProductBarcode,
    ProductCategory,
    ProductUnit,
    Supplier,
    SupplierGroup,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.models.platform import Currency, Tax, UnitOfMeasure
from app.services.audit_service import AuditContext, AuditService
from app.services.numbering_service import NumberingService, slugify_code

#: Fields a client may set on an item, party or contact.
_PRODUCT_FIELDS = {
    column.key
    for column in Product.__mapper__.columns
    if column.key not in {"id", "company_id", "created_at", "updated_at", "deleted_at"}
}
_PARTY_FIELDS = {
    column.key
    for column in Customer.__mapper__.columns
    if column.key not in {"id", "company_id", "created_at", "updated_at", "deleted_at"}
}
_CONTACT_FIELDS = {
    column.key
    for column in Contact.__mapper__.columns
    if column.key not in {"id", "company_id", "created_at", "updated_at", "deleted_at"}
}


class MasterDataService:
    """Shared helpers for master data services."""

    def __init__(
        self, db: Session, company_id: uuid.UUID, *, user_id: uuid.UUID | None = None, audit: AuditService | None = None
    ) -> None:
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.audit = audit or AuditService(db, AuditContext(company_id=company_id, user_id=user_id))

    # ------------------------------------------------------------------ helpers
    def _clean(self, payload: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
        values = {
            key: value
            for key, value in payload.items()
            if key in allowed and value is not None
        }
        for key in list(values):
            if key.endswith("_id") and values[key] is not None:
                values[key] = as_uuid(values[key])
            elif key in {
                "credit_limit",
                "opening_balance",
                "purchase_price",
                "sales_price",
                "cost_price",
                "standard_cost",
                "min_stock",
                "max_stock",
                "reorder_level",
                "reorder_quantity",
            }:
                values[key] = as_decimal(values[key])
            elif key in {"tags", "settings_json", "extra_data"} and not isinstance(values[key], (dict, list)):
                raise ValidationFailure(f"{key} must be a JSON object or array")
        return values

    def code_for(self, model: type[Any], prefix: str, *, field: str = "code", column: str = "code") -> str:
        """Next sequential code (CUS-00007) inside the company."""
        digits = 5
        sequence = self.db.execute(
            select(func.count()).select_from(model).where(model.company_id == self.company_id)
        ).scalar_one()
        for attempt in range(sequence + 1, sequence + 500):
            candidate = f"{prefix}-{attempt:0{digits}d}"
            exists = self.db.execute(
                select(getattr(model, field)).where(
                    model.company_id == self.company_id, getattr(model, column) == candidate
                )
            ).scalars().first()
            if exists is None:
                return candidate
        raise BusinessRuleError(f"Could not allocate a unique {prefix} code")


class ProductService(MasterDataService):
    """Universal item master (stock, service, consumable, asset, kit, bundle)."""

    def create(self, payload: dict[str, Any]) -> Product:
        values = self._clean(payload, _PRODUCT_FIELDS)
        values.pop("id", None)
        if not values.get("name"):
            raise ValidationFailure("The item name is required")
        product_type = str(values.get("product_type") or ProductType.STOCK.value)
        if product_type not in {item.value for item in ProductType}:
            raise ValidationFailure(
                f"Unknown item type '{product_type}'", allowed=[item.value for item in ProductType]
            )
        values["product_type"] = product_type
        values.setdefault("sku", self._generate_sku(values["name"]))
        self._assert_unique_sku(values["sku"], values.get("barcode"))
        if product_type == ProductType.STOCK.value:
            values.setdefault("track_inventory", True)
        if values.get("track_batches") or values.get("track_expiry"):
            values["track_inventory"] = True
        self._validate_references(values)
        self._fill_price_defaults(values)
        product = Product(company_id=self.company_id, **values)
        self.db.add(product)
        self.db.flush()
        self.audit.log_create(product, entity_type="product", label=product.sku)
        return product

    def update(self, product_id: uuid.UUID, payload: dict[str, Any]) -> Product:
        product = self.get(product_id)
        values = self._clean(payload, _PRODUCT_FIELDS)
        if "sku" in values and values["sku"] != product.sku:
            self._assert_unique_sku(values["sku"], values.get("barcode"), exclude_id=product.id)
        self._validate_references(values, partial=True)
        from app.core.pagination import snapshot

        before = snapshot(product)
        for key, value in values.items():
            setattr(product, key, value)
        self.db.flush()
        self.audit.log_update(product, before, entity_type="product", label=product.sku)
        return product

    def get(self, product_id: uuid.UUID | str) -> Product:
        product = self.db.get(Product, as_uuid(product_id))
        if product is None or product.company_id != self.company_id:
            raise NotFoundError("Item not found", id=str(product_id))
        return product

    def set_units(self, product_id: uuid.UUID | str, rows: list[dict[str, Any]]) -> list[ProductUnit]:
        product = self.get(product_id)
        for row in list(product.units):
            self.db.delete(row)
        self.db.flush()
        created: list[ProductUnit] = []
        for index, row in enumerate(rows, start=1):
            unit_id = as_uuid(row.get("unit_id"))
            if unit_id is None:
                raise ValidationFailure(f"Unit row {index} needs a unit_id")
            factor = as_decimal(row.get("conversion_factor", row.get("factor", 1)))
            if factor <= 0:
                raise ValidationFailure(f"Unit row {index}: the conversion factor must be positive")
            link = ProductUnit(
                company_id=self.company_id,
                product_id=product.id,
                unit_id=unit_id,
                conversion_factor=factor,
                is_base=bool(row.get("is_base", False)),
                is_purchase_unit=bool(row.get("is_purchase_unit", True)),
                is_sales_unit=bool(row.get("is_sales_unit", True)),
                barcode=row.get("barcode"),
                price=as_decimal(row["price"]) if row.get("price") is not None else None,
            )
            self.db.add(link)
            created.append(link)
        if not any(link.is_base for link in created) and created:
            created[0].is_base = True
        self.db.flush()
        return created

    def set_barcodes(self, product_id: uuid.UUID | str, barcodes: list[dict[str, Any]]) -> list[ProductBarcode]:
        product = self.get(product_id)
        for row in list(product.barcodes):
            self.db.delete(row)
        self.db.flush()
        created: list[ProductBarcode] = []
        for index, row in enumerate(barcodes, start=1):
            code = str(row.get("barcode") or "").strip()
            if not code:
                raise ValidationFailure(f"Barcode row {index} is empty")
            self._assert_unique_sku(None, code, exclude_id=product.id)
            link = ProductBarcode(
                company_id=self.company_id,
                product_id=product.id,
                barcode=code,
                unit_id=as_uuid(row.get("unit_id")),
                pack_quantity=as_decimal(row.get("pack_quantity", 1)),
                is_primary=bool(row.get("is_primary", index == 1)),
            )
            self.db.add(link)
            created.append(link)
        self.db.flush()
        return created

    def price_for(
        self, product_id: uuid.UUID | str, *, price_list_id: uuid.UUID | None = None, quantity_value: Decimal | None = None
    ) -> Decimal:
        """Resolve the selling price: price list first, then the item's own price."""
        product = self.get(product_id)
        if price_list_id is not None:
            qty = as_decimal(quantity_value or 1)
            stmt = (
                select(PriceListItem)
                .where(
                    PriceListItem.company_id == self.company_id,
                    PriceListItem.price_list_id == price_list_id,
                    PriceListItem.product_id == product.id,
                    PriceListItem.deleted_at.is_(None),
                )
                .order_by(PriceListItem.min_quantity.desc())
            )
            for row in self.db.execute(stmt).scalars().all():
                if qty >= as_decimal(row.min_quantity or 0):
                    discount = as_decimal(row.discount_percent or 0)
                    return (as_decimal(row.price) * (Decimal("1") - discount / Decimal("100"))).quantize(
                        Decimal("0.0001")
                    )
        return as_decimal(product.sales_price or 0)

    def search(self, term: str, *, limit: int = 25) -> list[Product]:
        pattern = f"%{term}%"
        return list(
            self.db.execute(
                select(Product)
                .where(
                    Product.company_id == self.company_id,
                    Product.deleted_at.is_(None),
                    or_(
                        Product.name.ilike(pattern),
                        Product.name_ar.ilike(pattern),
                        Product.sku.ilike(pattern),
                        Product.barcode.ilike(pattern),
                    ),
                )
                .order_by(Product.name)
                .limit(limit)
            ).scalars().all()
        )

    # ------------------------------------------------------------------ private
    def _generate_sku(self, name: str) -> str:
        base = slugify_code(name, max_length=12)
        sequence = self.db.execute(
            select(func.count()).select_from(Product).where(Product.company_id == self.company_id)
        ).scalar_one()
        for attempt in range(sequence + 1, sequence + 500):
            candidate = f"{base}-{attempt:04d}"
            exists = self.db.execute(
                select(Product.id).where(Product.company_id == self.company_id, Product.sku == candidate)
            ).first()
            if exists is None:
                return candidate
        raise BusinessRuleError("Could not allocate a unique SKU")

    def _assert_unique_sku(
        self, sku: str | None, barcode: str | None, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        if sku:
            stmt = select(Product.id).where(Product.company_id == self.company_id, Product.sku == sku)
            if exclude_id:
                stmt = stmt.where(Product.id != exclude_id)
            if self.db.execute(stmt).first() is not None:
                raise ConflictError(f"An item with SKU '{sku}' already exists")
        if barcode:
            stmt = select(Product.id).where(Product.company_id == self.company_id, Product.barcode == barcode)
            if exclude_id:
                stmt = stmt.where(Product.id != exclude_id)
            if self.db.execute(stmt).first() is not None:
                raise ConflictError(f"An item with barcode '{barcode}' already exists")
            duplicate = self.db.execute(
                select(ProductBarcode.id).where(
                    ProductBarcode.company_id == self.company_id, ProductBarcode.barcode == barcode
                )
            ).first()
            if duplicate is not None:
                raise ConflictError(f"Barcode '{barcode}' is already assigned to another item")

    def _validate_references(self, values: dict[str, Any], *, partial: bool = False) -> None:
        checks: list[tuple[str, type[Any], str]] = [
            ("unit_id", UnitOfMeasure, "Unit"),
            ("category_id", ProductCategory, "Category"),
            ("sales_tax_id", Tax, "Sales tax"),
            ("purchase_tax_id", Tax, "Purchase tax"),
        ]
        for field, model, label in checks:
            value = values.get(field)
            if value is None:
                continue
            row = self.db.get(model, value)
            if row is None:
                raise NotFoundError(f"{label} not found", id=str(value))
            if hasattr(row, "company_id") and row.company_id not in (None, self.company_id):
                raise ValidationFailure(f"{label} belongs to another company")

    def _fill_price_defaults(self, values: dict[str, Any]) -> None:
        if values.get("sales_price") in (None, Decimal("0")) and values.get("cost_price"):
            values["sales_price"] = as_decimal(values["cost_price"])
        if values.get("cost_price") in (None, Decimal("0")) and values.get("purchase_price"):
            values["cost_price"] = as_decimal(values["purchase_price"])


class PartyService(MasterDataService):
    """Customers and suppliers share almost every rule."""

    def create_customer(self, payload: dict[str, Any]) -> Customer:
        values = self._clean(payload, _PARTY_FIELDS)
        if not values.get("name"):
            raise ValidationFailure("The customer name is required")
        values.setdefault("code", self.code_for(Customer, "CUS"))
        self._assert_unique_code(Customer, values["code"], values.get("email"))
        self._validate_party_refs(values, Customer)
        customer = Customer(company_id=self.company_id, **self._party_defaults(values))
        self.db.add(customer)
        self.db.flush()
        self.audit.log_create(customer, entity_type="customer", label=customer.code)
        return customer

    def update_customer(self, customer_id: uuid.UUID, payload: dict[str, Any]) -> Customer:
        customer = self.get_customer(customer_id)
        values = self._clean(payload, _PARTY_FIELDS)
        if "code" in values and values["code"] != customer.code:
            self._assert_unique_code(Customer, values["code"], exclude_id=customer.id)
        self._validate_party_refs(values, Customer)
        from app.core.pagination import snapshot

        before = snapshot(customer)
        for key, value in values.items():
            if key not in {"credit_limit_used", "balance_amount"}:
                setattr(customer, key, value)
        self.db.flush()
        self.audit.log_update(customer, before, entity_type="customer", label=customer.code)
        return customer

    def create_supplier(self, payload: dict[str, Any]) -> Supplier:
        values = self._clean(payload, _PARTY_FIELDS)
        if not values.get("name"):
            raise ValidationFailure("The supplier name is required")
        values.setdefault("code", self.code_for(Supplier, "SUP"))
        self._assert_unique_code(Supplier, values["code"], values.get("email"))
        self._validate_party_refs(values, Supplier)
        supplier = Supplier(company_id=self.company_id, **self._party_defaults(values))
        self.db.add(supplier)
        self.db.flush()
        self.audit.log_create(supplier, entity_type="supplier", label=supplier.code)
        return supplier

    def update_supplier(self, supplier_id: uuid.UUID, payload: dict[str, Any]) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        values = self._clean(payload, _PARTY_FIELDS)
        if "code" in values and values["code"] != supplier.code:
            self._assert_unique_code(Supplier, values["code"], exclude_id=supplier.id)
        self._validate_party_refs(values, Supplier)
        from app.core.pagination import snapshot

        before = snapshot(supplier)
        for key, value in values.items():
            if key not in {"credit_limit_used", "balance_amount"}:
                setattr(supplier, key, value)
        self.db.flush()
        self.audit.log_update(supplier, before, entity_type="supplier", label=supplier.code)
        return supplier

    def get_customer(self, customer_id: uuid.UUID | str) -> Customer:
        customer = self.db.get(Customer, as_uuid(customer_id))
        if customer is None or customer.company_id != self.company_id:
            raise NotFoundError("Customer not found", id=str(customer_id))
        return customer

    def get_supplier(self, supplier_id: uuid.UUID | str) -> Supplier:
        supplier = self.db.get(Supplier, as_uuid(supplier_id))
        if supplier is None or supplier.company_id != self.company_id:
            raise NotFoundError("Supplier not found", id=str(supplier_id))
        return supplier

    def credit_position(self, customer_id: uuid.UUID | str) -> dict[str, Any]:
        """Outstanding balance, credit limit and available credit."""
        from app.models.sales import SalesInvoice

        customer = self.get_customer(customer_id)
        outstanding = self.db.execute(
            select(func.coalesce(func.sum(SalesInvoice.balance_amount), 0)).where(
                SalesInvoice.company_id == self.company_id,
                SalesInvoice.customer_id == customer.id,
                SalesInvoice.status.in_(["posted", "partially_fulfilled"]),
            )
        ).scalar_one()
        limit = as_decimal(customer.credit_limit or 0)
        outstanding = as_decimal(outstanding)
        return {
            "customer_id": str(customer.id),
            "credit_limit": str(limit),
            "outstanding": str(outstanding),
            "available": str(limit - outstanding),
            "credit_days": customer.credit_days,
            "on_hold": bool(customer.is_credit_hold),
        }

    def add_contact(self, *, party_type: str, party_id: uuid.UUID | str, payload: dict[str, Any]) -> Contact:
        owner_id = as_uuid(party_id)
        if party_type == PartyType.CUSTOMER.value:
            self.get_customer(owner_id)
        elif party_type == PartyType.SUPPLIER.value:
            self.get_supplier(owner_id)
        else:
            raise ValidationFailure("party_type must be 'customer' or 'supplier'")
        values = self._clean(payload, _CONTACT_FIELDS)
        if not values.get("first_name") and not values.get("last_name"):
            raise ValidationFailure("The contact needs at least a first or last name")
        values["party_type"] = party_type
        values["customer_id"] = owner_id if party_type == PartyType.CUSTOMER.value else None
        values["supplier_id"] = owner_id if party_type == PartyType.SUPPLIER.value else None
        contact = Contact(company_id=self.company_id, **values)
        self.db.add(contact)
        self.db.flush()
        self.audit.log_create(contact, entity_type="contact", label=contact.full_name if hasattr(contact, "full_name") else values.get("first_name"))
        return contact

    def set_supplier_product(self, supplier_id: uuid.UUID | str, payload: dict[str, Any]) -> SupplierProduct:
        supplier = self.get_supplier(supplier_id)
        product_id = as_uuid(payload.get("product_id"))
        if product_id is None:
            raise ValidationFailure("A product is required")
        existing = self.db.execute(
            select(SupplierProduct).where(
                SupplierProduct.company_id == self.company_id,
                SupplierProduct.supplier_id == supplier.id,
                SupplierProduct.product_id == product_id,
            )
        ).scalars().first()
        price = as_decimal(payload.get("last_price", payload.get("price", 0)))
        if existing is None:
            existing = SupplierProduct(
                company_id=self.company_id,
                supplier_id=supplier.id,
                product_id=product_id,
                supplier_sku=payload.get("supplier_sku"),
                last_price=price,
                currency_code=payload.get("currency_code"),
                lead_time_days=payload.get("lead_time_days"),
                min_order_quantity=as_decimal(payload.get("min_order_quantity", 0)),
                is_preferred=bool(payload.get("is_preferred", False)),
            )
            self.db.add(existing)
        else:
            existing.last_price = price
            for field in ("supplier_sku", "currency_code", "lead_time_days", "min_order_quantity", "is_preferred"):
                if payload.get(field) is not None:
                    setattr(existing, field, payload[field])
        self.db.flush()
        if price > 0:
            self.db.add(
                SupplierPriceHistory(
                    company_id=self.company_id,
                    supplier_id=supplier.id,
                    product_id=product_id,
                    price=price,
                    currency_code=payload.get("currency_code"),
                    effective_date=payload.get("effective_date"),
                    source=payload.get("source") or "manual",
                )
            )
            self.db.flush()
        return existing

    # ------------------------------------------------------------------ private
    def _party_defaults(self, values: dict[str, Any]) -> dict[str, Any]:
        values.setdefault("currency_code", self._base_currency())
        values.setdefault("credit_limit", Decimal("0"))
        values.setdefault("credit_days", 0)
        values.setdefault("is_active", True)
        return values

    def _base_currency(self) -> str:
        from app.models.platform import Company

        company = self.db.get(Company, self.company_id)
        return (company.base_currency_code if company else None) or "USD"

    def _assert_unique_code(
        self, model: type[Any], code: str, email: str | None = None, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        if code:
            stmt = select(model.id).where(model.company_id == self.company_id, model.code == code)
            if exclude_id:
                stmt = stmt.where(model.id != exclude_id)
            if self.db.execute(stmt).first() is not None:
                raise ConflictError(f"{model.__name__} code '{code}' already exists")
        if email:
            stmt = select(model.id).where(model.company_id == self.company_id, model.email == email)
            if exclude_id:
                stmt = stmt.where(model.id != exclude_id)
            if self.db.execute(stmt).first() is not None:
                raise ConflictError(f"Email '{email}' is already used by another {model.__name__.lower()}")

    def _validate_party_refs(self, values: dict[str, Any], model: type[Any]) -> None:
        checks: list[tuple[str, type[Any], str]] = []
        if model is Customer:
            checks = [
                ("customer_group_id", CustomerGroup, "Customer group"),
                ("price_list_id", PriceList, "Price list"),
            ]
        else:
            checks = [("supplier_group_id", SupplierGroup, "Supplier group")]
        checks.append(("currency_code", Currency, "Currency"))
        for field, target, label in checks:
            value = values.get(field)
            if value is None:
                continue
            if target is Currency:
                row = self.db.execute(select(Currency).where(Currency.code == str(value).upper())).scalars().first()
                if row is None:
                    raise NotFoundError(f"{label} {value} is not configured")
                values[field] = row.code
                continue
            row = self.db.get(target, as_uuid(value))
            if row is None or (hasattr(row, "company_id") and row.company_id != self.company_id):
                raise NotFoundError(f"{label} not found", id=str(value))


class ContactService(MasterDataService):
    """Contacts of customers and suppliers."""

    def list_for(self, *, party_type: str, party_id: uuid.UUID) -> list[Contact]:
        stmt = select(Contact).where(
            Contact.company_id == self.company_id,
            Contact.deleted_at.is_(None),
            Contact.party_type == party_type,
        )
        if party_type == PartyType.CUSTOMER.value:
            stmt = stmt.where(Contact.customer_id == party_id)
        elif party_type == PartyType.SUPPLIER.value:
            stmt = stmt.where(Contact.supplier_id == party_id)
        elif party_type == "other":
            pass
        else:
            raise ValidationFailure("party_type must be 'customer' or 'supplier'")
        return list(self.db.execute(stmt.order_by(Contact.first_name, Contact.last_name)).scalars().all())

    def delete(self, contact_id: uuid.UUID) -> None:
        contact = self.db.get(Contact, contact_id)
        if contact is None or contact.company_id != self.company_id:
            raise NotFoundError("Contact not found", id=str(contact_id))
        self.audit.log_delete(contact, entity_type="contact", label=contact.first_name)
        self.db.delete(contact)
        self.db.flush()


def next_document_code(db: Session, company_id: uuid.UUID, document_type: str, prefix: str) -> str:
    """Small helper for services that need a code without a numbering record."""
    return NumberingService(db, company_id).next_number(document_type)


__all__ = [
    "ContactService",
    "MasterDataService",
    "PartyService",
    "ProductService",
    "next_document_code",
]
