"""Demonstration data (development / evaluation only).

The seeder never invents business logic: it drives the same services the API
uses (bootstrap -> master data -> inventory opening -> sales chain) so the demo
company is a genuine, fully posted dataset.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import set_session_tenant
from app.core.enums import MovementType, ProductType
from app.models.identity import User
from app.models.masterdata import (
    Customer,
    CustomerGroup,
    Product,
    ProductCategory,
    Supplier,
    SupplierGroup,
    Warehouse,
)
from app.models.platform import Company, UnitOfMeasure
from app.services.bootstrap_service import BootstrapService
from app.services.inventory_service import InventoryService, StockMove
from app.services.posting_service import money
from app.services.purchasing_service import GoodsReceiptService, PurchaseInvoiceService, PurchaseOrderService
from app.services.sales_service import DeliveryNoteService, SalesInvoiceService, SalesOrderService

DEMO_COMPANY_CODE = "DEMO"
DEMO_USERS: list[dict[str, Any]] = [
    {
        "email": "admin@kayan-demo.com",
        "password": "Admin@12345",
        "full_name": "System Administrator",
        "full_name_ar": "مدير النظام",
        "roles": ["company_admin"],
        "job_title": "System Administrator",
    },
    {
        "email": "manager@kayan-demo.com",
        "password": "Manager@12345",
        "full_name": "General Manager",
        "full_name_ar": "المدير العام",
        "roles": ["general_manager"],
        "job_title": "General Manager",
    },
    {
        "email": "sales@kayan-demo.com",
        "password": "Sales@12345",
        "full_name": "Sales Representative",
        "full_name_ar": "مندوب المبيعات",
        "roles": ["sales_manager", "sales_rep"],
        "job_title": "Sales Manager",
    },
    {
        "email": "store@kayan-demo.com",
        "password": "Store@12345",
        "full_name": "Warehouse Keeper",
        "full_name_ar": "أمين المخزن",
        "roles": ["warehouse_manager"],
        "job_title": "Warehouse Manager",
    },
    {
        "email": "accountant@kayan-demo.com",
        "password": "Account@12345",
        "full_name": "Chief Accountant",
        "full_name_ar": "رئيس الحسابات",
        "roles": ["accountant"],
        "job_title": "Chief Accountant",
    },
    {
        "email": "cashier@kayan-demo.com",
        "password": "Cashier@12345",
        "full_name": "POS Cashier",
        "full_name_ar": "كاشير نقطة البيع",
        "roles": ["pos_cashier"],
        "job_title": "Cashier",
    },
]

DEMO_CUSTOMERS = [
    ("CUS-0001", "Al Noor Trading", "شركة النور للتجارة", "Cairo", "10.10.1.11", "15.5.2.22", Decimal("50000"), 30),
    ("CUS-0002", "Delta Distribution", "دلتا للتوزيع", "Mansoura", "20.20.3.33", "30.30.4.44", Decimal("25000"), 30),
    ("CUS-0003", "Cairo Retail Group", "مجموعة القاهرة للتجزئة", "Giza", "40.40.5.55", "50.50.6.66", Decimal("80000"), 45),
    ("CUS-0004", "Sahara Contracting", "الصحراء للمقاولات", "Assiut", "60.60.7.77", "70.70.8.88", Decimal("100000"), 60),
    ("CUS-0005", "Walk-in Customer", "عميل نقدي", "Minya", None, None, Decimal("0"), 0),
]

DEMO_SUPPLIERS = [
    ("SUP-0001", "General Electric Supply", "العامة للتوريدات الكهربائية", "Cairo", "100.1.2.3", 15, Decimal("3")),
    ("SUP-0002", "Al Amal Hardware", "الأمل للأدوات", "Alexandria", "200.2.3.4", 20, Decimal("2")),
    ("SUP-0003", "Tech Components Ltd", "تك للمكونات", "Cairo", "300.3.4.5", 30, Decimal("1.5")),
]

DEMO_PRODUCTS = [
    ("SKU-1001", "Solar Panel 550W", "لوح شمسي 550 وات", "PCS", Decimal("4800"), Decimal("6200"), 40, ProductType.STOCK),
    ("SKU-1002", "Solar Inverter 5kW", "إنفرتر شمسي 5 كيلو", "PCS", Decimal("12500"), Decimal("15900"), 15, ProductType.STOCK),
    ("SKU-1003", "Battery 200Ah", "بطارية 200 أمبير", "PCS", Decimal("5400"), Decimal("7100"), 25, ProductType.STOCK),
    ("SKU-1004", "Mounting Rail 4m", "قضيب تثبيت 4 متر", "MTR", Decimal("180"), Decimal("260"), 200, ProductType.STOCK),
    ("SKU-1005", "DC Cable 6mm (per meter)", "كابل مستمر 6 مم", "MTR", Decimal("35"), Decimal("55"), 500, ProductType.STOCK),
    ("SKU-1006", "Installation Service", "خدمة تركيب", "HR", Decimal("0"), Decimal("900"), 0, ProductType.SERVICE),
    ("SKU-1007", "Maintenance Contract (annual)", "عقد صيانة سنوي", "SET", Decimal("0"), Decimal("4500"), 0, ProductType.SERVICE),
]


class SeedService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --------------------------------------------------------------- company
    def company_exists(self, code: str = DEMO_COMPANY_CODE) -> bool:
        return self.db.execute(select(Company).where(Company.code == code)).scalars().first() is not None

    def create_demo_company(self, *, seed_transactions: bool = True) -> dict[str, Any]:
        bootstrap = BootstrapService(self.db)
        provisioned = bootstrap.create_company(
            {
                "code": DEMO_COMPANY_CODE,
                "name": "Kayan Demo Company",
                "name_ar": "شركة كيان التجريبية",
                "legal_name": "Kayan Demo Company LLC",
                "industry": "Renewable Energy & Trading",
                "base_currency_code": "EGP",
                "country_code": "EG",
                "default_language": "ar",
                "phone": "+20 2 1234 5678",
                "email": "info@kayan-demo.com",
                "fiscal_year_start_month": 1,
                "valuation_method": "average",
                "taxes": [],
            }
        )
        company: Company = provisioned["company"]
        branch = provisioned["branch"]
        warehouse = provisioned["warehouse"]
        set_session_tenant(self.db, company.id)

        units = bootstrap.ensure_units(company.id)
        term = provisioned["payment_terms"]

        users: dict[str, Any] = {}
        # Users are created without per-company role duplication.
        for user_payload in DEMO_USERS:
            existing = self.db.execute(
                select(User).where(User.email == user_payload["email"])
            ).scalars().first()
            if existing is not None:
                users[user_payload["email"]] = existing
                continue
            user = bootstrap.create_user(
                email=user_payload["email"],
                password=user_payload["password"],
                full_name=user_payload["full_name"],
                company_id=company.id,
                roles=user_payload["roles"],
                branch_ids=[branch.id],
                warehouse_ids=[warehouse.id],
                job_title=user_payload.get("job_title"),
            )
            user.full_name_ar = user_payload.get("full_name_ar")
            users[user_payload["email"]] = user
        self.db.flush()
        admin = users["admin@kayan-demo.com"]

        customer_groups = self._ensure_customer_groups(company)
        supplier_groups = self._ensure_supplier_groups(company)
        category = self._ensure_category(company)
        customers = self._ensure_customers(company, customer_groups, term["NET30"].id)
        suppliers = self._ensure_suppliers(company, supplier_groups, term["NET30"].id)
        products = self._ensure_products(company, category, units)

        result: dict[str, Any] = {
            "company": company,
            "branch": branch,
            "warehouse": warehouse,
            "users": users,
            "admin": admin,
            "customers": customers,
            "suppliers": suppliers,
            "products": products,
            "units": units,
            "fiscal_year": provisioned["fiscal_year"],
        }
        if seed_transactions:
            result["opening_stock"] = self._seed_opening_stock(company, warehouse, products, admin.id)
        return result

    # ------------------------------------------------------------ master data
    def _ensure_customer_groups(self, company: Company) -> dict[str, CustomerGroup]:
        groups: dict[str, CustomerGroup] = {}
        for code, name, name_ar in [("RETAIL", "Retail", "تجزئة"), ("WHOLESALE", "Wholesale", "جملة")]:
            group = self.db.execute(
                select(CustomerGroup).where(CustomerGroup.company_id == company.id, CustomerGroup.code == code)
            ).scalars().first()
            if group is None:
                group = CustomerGroup(company_id=company.id, code=code, name=name, name_ar=name_ar)
                self.db.add(group)
                self.db.flush()
            groups[code] = group
        return groups

    def _ensure_supplier_groups(self, company: Company) -> dict[str, SupplierGroup]:
        groups: dict[str, SupplierGroup] = {}
        for code, name, name_ar in [("LOCAL", "Local Suppliers", "موردون محليون"), ("IMPORT", "Imported", "مستوردون")]:
            group = self.db.execute(
                select(SupplierGroup).where(SupplierGroup.company_id == company.id, SupplierGroup.code == code)
            ).scalars().first()
            if group is None:
                group = SupplierGroup(company_id=company.id, code=code, name=name, name_ar=name_ar)
                self.db.add(group)
                self.db.flush()
            groups[code] = group
        return groups

    def _ensure_category(self, company: Company) -> ProductCategory:
        category = self.db.execute(
            select(ProductCategory).where(ProductCategory.company_id == company.id, ProductCategory.code == "SOLAR")
        ).scalars().first()
        if category is None:
            category = ProductCategory(
                company_id=company.id, code="SOLAR", name="Solar Equipment", name_ar="معدات الطاقة الشمسية"
            )
            self.db.add(category)
            self.db.flush()
        return category

    def _ensure_customers(
        self, company: Company, groups: dict[str, CustomerGroup], payment_term_id: uuid.UUID
    ) -> list[Customer]:
        customers: list[Customer] = []
        for code, name, name_ar, city, phone, mobile, credit_limit, credit_days in DEMO_CUSTOMERS:
            customer = self.db.execute(
                select(Customer).where(Customer.company_id == company.id, Customer.code == code)
            ).scalars().first()
            if customer is None:
                customer = Customer(
                    company_id=company.id,
                    code=code,
                    name=name,
                    name_ar=name_ar,
                    customer_group_id=groups["WHOLESALE"].id if credit_limit else groups["RETAIL"].id,
                    email=f"{code.lower()}@kayan-demo.com",
                    phone=phone,
                    mobile=mobile,
                    city=city,
                    country_code=company.country_code,
                    credit_limit=credit_limit,
                    credit_days=credit_days,
                    payment_term_id=payment_term_id,
                    currency_code=company.base_currency_code,
                    is_active=True,
                )
                self.db.add(customer)
                self.db.flush()
            customers.append(customer)
        return customers

    def _ensure_suppliers(
        self, company: Company, groups: dict[str, SupplierGroup], payment_term_id: uuid.UUID
    ) -> list[Supplier]:
        suppliers: list[Supplier] = []
        for code, name, name_ar, city, phone, lead_time, rating in DEMO_SUPPLIERS:
            supplier = self.db.execute(
                select(Supplier).where(Supplier.company_id == company.id, Supplier.code == code)
            ).scalars().first()
            if supplier is None:
                supplier = Supplier(
                    company_id=company.id,
                    code=code,
                    name=name,
                    name_ar=name_ar,
                    supplier_group_id=groups["LOCAL"].id,
                    phone=phone,
                    city=city,
                    country_code=company.country_code,
                    credit_days=30,
                    payment_term_id=payment_term_id,
                    currency_code=company.base_currency_code,
                    lead_time_days=lead_time,
                    rating=rating,
                    is_active=True,
                )
                self.db.add(supplier)
                self.db.flush()
            suppliers.append(supplier)
        return suppliers

    def _ensure_products(
        self, company: Company, category: ProductCategory, units: dict[str, UnitOfMeasure]
    ) -> list[Product]:
        products: list[Product] = []
        for sku, name, name_ar, unit_code, cost, price, reorder, product_type in DEMO_PRODUCTS:
            product = self.db.execute(
                select(Product).where(Product.company_id == company.id, Product.sku == sku)
            ).scalars().first()
            if product is None:
                unit = units[unit_code]
                product = Product(
                    company_id=company.id,
                    sku=sku,
                    name=name,
                    name_ar=name_ar,
                    product_type=product_type.value,
                    category_id=category.id,
                    unit_id=unit.id,
                    purchase_price=cost,
                    sales_price=price,
                    cost_price=cost,
                    track_inventory=product_type != ProductType.SERVICE,
                    min_stock=Decimal(reorder) * Decimal("0.25"),
                    max_stock=Decimal(reorder) * Decimal("4"),
                    reorder_level=Decimal(reorder),
                    reorder_quantity=Decimal(reorder),
                    lead_time_days=14,
                    is_sellable=True,
                    is_purchasable=product_type != ProductType.SERVICE,
                )
                self.db.add(product)
                self.db.flush()
            products.append(product)
        return products

    # ---------------------------------------------------------------- opening
    def _seed_opening_stock(
        self, company: Company, warehouse, products: list[Product], user_id: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        inventory = InventoryService(self.db, company.id)
        posted: list[dict[str, Any]] = []
        for product in products:
            if not product.track_inventory:
                continue
            if inventory.stock_on_hand(product.id, warehouse.id) > 0:
                continue
            quantity = Decimal(product.reorder_level or 0) * Decimal("2") or Decimal("50")
            result = inventory.move(
                StockMove(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity=quantity,
                    movement_type=MovementType.OPENING,
                    unit_cost=Decimal(product.cost_price or 0),
                    reference_type="opening",
                    notes="Opening balance (demo seed)",
                    allow_negative=True,
                    extra_data={"seeded_by": str(user_id) if user_id else None},
                )
            )
            posted.append(
                {
                    "product": product.sku,
                    "quantity": str(result.balance_quantity),
                    "value": str(result.balance_value),
                }
            )
        self.db.flush()
        if posted:
            total_value = money(sum((Decimal(item["value"]) for item in posted), Decimal("0")))
            self._post_opening_journal(company, warehouse, total_value, user_id)
        return posted

    def _post_opening_journal(self, company: Company, warehouse, total_value: Decimal, user_id: uuid.UUID | None) -> Any:
        """Journalise the opening inventory so the GL and the stock ledger agree."""
        if total_value <= 0:
            return None
        from app.services.posting_service import DocumentPostingContext, EntryLine, PostingService

        posting = PostingService(self.db, company.id)
        inventory_account = posting.resolve_account(
            "inventory", document_type="opening_balance", fallback_code="1310"
        )
        equity_account = posting.resolve_account(
            "opening_balance_equity", document_type="opening_balance", fallback_code="3110"
        )
        entry = posting.build_entry(
            context=DocumentPostingContext(
                document_type="opening_balance",
                document_id=uuid.uuid4(),
                document_no="OPENING",
                document_date=date.today(),
                description="Opening inventory balance (demo seed)",
            ),
            lines=[
                EntryLine(
                    account_id=inventory_account.id,
                    debit=total_value,
                    description="Opening inventory",
                    warehouse_id=warehouse.id,
                ),
                EntryLine(
                    account_id=equity_account.id,
                    credit=total_value,
                    description="Opening balance equity",
                ),
            ],
            entry_type="opening_balance",
            reference="OPENING",
            auto_post=True,
            user_id=user_id,
        )
        self.db.flush()
        return entry.id

    # ------------------------------------------------------------ demo flows
    def run_demo_transactions(self, *, orders: int = 6, purchases: int = 3) -> dict[str, Any]:
        """Create a handful of realistic, fully posted sales & purchase documents."""
        company = self.db.execute(select(Company).where(Company.code == DEMO_COMPANY_CODE)).scalars().first()
        if company is None:
            raise RuntimeError("Demo company not provisioned; call create_demo_company first")
        set_session_tenant(self.db, company.id)

        admin = self.db.execute(
            select(User).where(User.email == "admin@kayan-demo.com")
        ).scalars().first()
        sales_user = self.db.execute(
            select(User).where(User.email == "sales@kayan-demo.com")
        ).scalars().first()
        warehouse = self.db.execute(
            select(Warehouse).where(Warehouse.company_id == company.id)
        ).scalars().first()
        customers = list(
            self.db.execute(
                select(Customer).where(Customer.company_id == company.id, Customer.credit_limit > 0)
            ).scalars().all()
        )
        suppliers = list(self.db.execute(select(Supplier).where(Supplier.company_id == company.id)).scalars().all())
        stock_products = list(
            self.db.execute(
                select(Product).where(Product.company_id == company.id, Product.track_inventory.is_(True))
            ).scalars().all()
        )
        service_products = list(
            self.db.execute(
                select(Product).where(Product.company_id == company.id, Product.track_inventory.is_(False))
            ).scalars().all()
        )

        random.seed(7)
        sales_documents: list[dict[str, Any]] = []
        sales_service = SalesOrderService(self.db, company.id, user_id=sales_user.id if sales_user else None)
        invoice_service = SalesInvoiceService(self.db, company.id, user_id=sales_user.id if sales_user else None)
        delivery_service = DeliveryNoteService(self.db, company.id, user_id=sales_user.id if sales_user else None)

        trackable = {product.id: product.track_inventory for product in stock_products + service_products}
        for index in range(orders):
            customer = customers[index % len(customers)]
            lines = []
            for product in random.sample(stock_products, k=min(2, len(stock_products))):
                lines.append({"product_id": str(product.id), "quantity": str(random.choice([2, 3, 5])),
                              "unit_price": str(product.sales_price)})
            if service_products:
                service = random.choice(service_products)
                lines.append({"product_id": str(service.id), "quantity": "1", "unit_price": str(service.sales_price)})
            order = sales_service.create(
                {
                    "customer_id": str(customer.id),
                    "document_date": date.today() - timedelta(days=orders - index),
                    "warehouse_id": str(warehouse.id),
                    "customer_reference": f"PO-{1000 + index}",
                    "lines": lines,
                    "notes": "Demo sales order",
                }
            )
            sales_service.confirm(order.id, allow_credit_override=True)
            delivery = sales_service.create_delivery(
                order.id,
                {
                    "document_date": order.document_date,
                    "lines": [
                        {"order_line_id": str(line.id), "quantity": str(line.quantity)}
                        for line in order.lines
                        if trackable.get(line.product_id)
                    ],
                },
            )
            delivery_service.post(delivery)
            invoice = sales_service.create_invoice(
                order.id,
                {
                    "document_date": order.document_date,
                    "delivery_note_id": str(delivery.id),
                    "allow_credit_override": True,
                    "lines": [{"order_line_id": str(line.id), "quantity": str(line.quantity)} for line in order.lines],
                },
            )
            invoice_service.post(invoice)
            sales_documents.append(
                {
                    "order": order.document_no,
                    "delivery": delivery.document_no,
                    "invoice": invoice.document_no,
                    "total": str(invoice.total_amount),
                }
            )
            self.db.flush()

        purchase_documents: list[dict[str, Any]] = []
        po_service = PurchaseOrderService(self.db, company.id, user_id=admin.id if admin else None)
        receipt_service = GoodsReceiptService(self.db, company.id, user_id=admin.id if admin else None)
        pi_service = PurchaseInvoiceService(self.db, company.id, user_id=admin.id if admin else None)
        for index in range(purchases):
            supplier = suppliers[index % len(suppliers)]
            lines = []
            for product in random.sample(stock_products, k=min(3, len(stock_products))):
                lines.append(
                    {
                        "product_id": str(product.id),
                        "quantity": str(random.choice([4, 6, 10])),
                        "unit_price": str(product.purchase_price),
                    }
                )
            order = po_service.create(
                {
                    "supplier_id": str(supplier.id),
                    "document_date": date.today() - timedelta(days=purchases - index),
                    "warehouse_id": str(warehouse.id),
                    "supplier_reference": f"REF-{2000 + index}",
                    "lines": lines,
                    "notes": "Demo purchase order",
                }
            )
            po_service.approve(order)
            receipt = po_service.create_receipt(
                order.id,
                {
                    "warehouse_id": str(warehouse.id),
                    "document_date": order.document_date,
                    "lines": [
                        {"order_line_id": str(line.id), "quantity": str(line.quantity)} for line in order.lines
                    ],
                },
            )
            receipt_service.post(receipt)
            invoice = po_service.create_invoice(
                order.id,
                {
                    "goods_receipt_id": str(receipt.id),
                    "supplier_invoice_no": f"INV-{3000 + index}",
                    "document_date": order.document_date,
                    "lines": [
                        {
                            "order_line_id": str(line.id),
                            "goods_receipt_line_id": str(receipt_line.id),
                            "quantity": str(line.quantity),
                        }
                        for line, receipt_line in zip(order.lines, receipt.lines)
                    ],
                },
            )
            pi_service.post(invoice)
            purchase_documents.append(
                {
                    "order": order.document_no,
                    "receipt": receipt.document_no,
                    "invoice": invoice.document_no,
                    "total": str(invoice.total_amount),
                }
            )
            self.db.flush()

        return {"sales": sales_documents, "purchases": purchase_documents}
