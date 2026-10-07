"""Shared pytest fixtures.

The suite runs against a throwaway SQLite database so it needs no services.  The
demo company is provisioned once per session through the same seeding service
the development environment uses, which keeps the tests honest about the real
bootstrap path.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

TMP_DIR = Path(tempfile.mkdtemp(prefix="kayan-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TMP_DIR / 'kayan_test.db'}")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("STORAGE_DIR", str(TMP_DIR / "storage"))
os.environ.setdefault("BACKUP_DIR", str(TMP_DIR / "backups"))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

import app.models_registry  # noqa: F401,E402  (registers every mapper)
from app.core.database import Base, SessionLocal, engine, set_session_tenant  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services.seed_service import SeedService  # noqa: E402

ADMIN_EMAIL = "admin@kayan-demo.com"
ADMIN_PASSWORD = "Admin@12345"
CASHIER_EMAIL = "cashier@kayan-demo.com"
CASHIER_PASSWORD = "Cashier@12345"
ACCOUNTANT_EMAIL = "accountant@kayan-demo.com"
ACCOUNTANT_PASSWORD = "Account@12345"


@pytest.fixture(scope="session")
def seeded() -> dict[str, Any]:
    """Create the schema and provision the demo company once per session."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seeder = SeedService(session)
        data = seeder.create_demo_company(seed_transactions=False)
        company = data["company"]
        set_session_tenant(session, company.id)
        session.commit()
        seeder._seed_opening_stock(company, data["warehouse"], data["products"], data["admin"].id)
        session.commit()
        return {
            "company_id": company.id,
            "company_code": company.code,
            "warehouse_id": data["warehouse"].id,
            "branch_id": data["branch"].id,
            "product_ids": {product.sku: product.id for product in data["products"]},
            "admin_id": data["admin"].id,
        }


@pytest.fixture(scope="session")
def client(seeded: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def cashier_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": CASHIER_EMAIL, "password": CASHIER_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def accountant_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": ACCOUNTANT_EMAIL, "password": ACCOUNTANT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def customer_id(client: TestClient, admin_headers: dict[str, str]) -> uuid.UUID:
    response = client.get("/api/v1/customers?page_size=1", headers=admin_headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["items"][0]["id"])


@pytest.fixture(scope="session")
def supplier_id(client: TestClient, admin_headers: dict[str, str]) -> uuid.UUID:
    response = client.get("/api/v1/suppliers?page_size=1", headers=admin_headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["items"][0]["id"])


@pytest.fixture(scope="session")
def pos_cash_account_id(client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]) -> uuid.UUID:
    response = client.get("/api/v1/pos/shifts", headers=admin_headers)
    assert response.status_code in (200, 404)
    response = client.get("/api/v1/accounts?q=cash", headers=admin_headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "the demo chart of accounts has no cash account"
    return uuid.UUID(items[0]["id"])


@pytest.fixture
def product_id(seeded: dict[str, Any]) -> uuid.UUID:
    return seeded["product_ids"]["SKU-1001"]


@pytest.fixture
def warehouse_id(seeded: dict[str, Any]) -> uuid.UUID:
    return seeded["warehouse_id"]
