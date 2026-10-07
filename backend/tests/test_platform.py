"""Platform level tests: health, authentication, RBAC and tenant isolation."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_health_and_metadata(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

    version = client.get("/api/v1/version")
    assert version.status_code == 200
    assert "inventory" in version.json()["modules"]


def test_openapi_is_versioned_and_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert len(schema["paths"]) > 500
    assert schema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert any(path.startswith("/api/v1/") for path in schema["paths"])


def test_login_refresh_and_me(client: TestClient) -> None:
    anonymous = client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401

    login = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["session_id"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["company"]["code"] == "DEMO"

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] != tokens["access_token"]


def test_bad_credentials_are_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "not-the-password"})
    assert response.status_code == 401


def test_session_revocation_invalidates_tokens(client: TestClient) -> None:
    login = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout = client.post("/api/v1/auth/logout", headers=headers, json={})
    assert logout.status_code in (200, 204)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_cashier_is_denied_privileged_modules(
    client: TestClient, cashier_headers: dict[str, str]
) -> None:
    for path in (
        "/api/v1/accounts",
        "/api/v1/journal-entries",
        "/api/v1/employees",
        "/api/v1/stock/ledger",
        "/api/v1/admin/companies",
    ):
        response = client.get(path, headers=cashier_headers)
        assert response.status_code == 403, f"{path} -> {response.status_code}"


def test_cashier_can_run_the_till(client: TestClient, cashier_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/pos/terminals", headers=cashier_headers).status_code in (200, 404)
    assert client.get("/api/v1/products", headers=cashier_headers).status_code == 200


def test_accountant_can_read_ledgers_but_not_manage_users(
    client: TestClient, accountant_headers: dict[str, str]
) -> None:
    assert client.get("/api/v1/journal-entries", headers=accountant_headers).status_code == 200
    assert client.get("/api/v1/reports/trial-balance", headers=accountant_headers).status_code == 200
    assert client.get("/api/v1/users", headers=accountant_headers).status_code == 200
    denied = client.post(
        "/api/v1/users",
        headers=accountant_headers,
        json={"email": "nope@example.com", "password": "Passw0rd!23", "full_name": "Nope"},
    )
    assert denied.status_code == 403


def test_permission_catalogue_matches_routers() -> None:
    """Every permission the routers ask for must exist in the catalogue."""
    import re
    from pathlib import Path

    from app.core.permissions import all_permission_codes

    known = set(all_permission_codes())
    pattern = re.compile(r"""(?:require|can|can_any)\(\s*["']([a-z0-9_.*]+)["']""")
    missing: set[str] = set()
    for path in Path("app/api/v1").glob("*.py"):
        for code in pattern.findall(path.read_text()):
            if code != "*" and code not in known:
                missing.add(code)
    assert not missing, f"unknown permission codes: {sorted(missing)}"


def test_role_templates_expand_to_catalogue_codes() -> None:
    from app.core.permissions import ROLE_TEMPLATES, expand_role_template

    for template in ROLE_TEMPLATES:
        _, permissions = expand_role_template(template)
        assert permissions, f"template {template} expands to nothing"


def test_tenant_isolation(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/admin/companies",
        headers=admin_headers,
        json={"name": "Isolation Co", "code": f"ISO{uuid.uuid4().hex[:6].upper()}", "currency_code": "USD"},
    )
    assert created.status_code == 201, created.text
    other_id = created.json()["id"]
    assert created.json()["provisioned"]["branch"]["code"]

    cross = client.get("/api/v1/products", headers={**admin_headers, "X-Company-Id": other_id})
    assert cross.status_code == 403

    profile = client.get(f"/api/v1/admin/companies/{other_id}", headers=admin_headers)
    assert profile.status_code == 403


def test_payload_dates_are_coerced(client: TestClient, admin_headers: dict[str, str], seeded: dict) -> None:
    """ISO strings in JSON must reach the services as date objects."""
    response = client.get("/api/v1/customers?page_size=1", headers=admin_headers)
    customer = response.json()["items"][0]["id"]
    order = client.post(
        "/api/v1/sales-orders",
        headers=admin_headers,
        json={
            "customer_id": customer,
            "document_date": "2026-04-01",
            "warehouse_id": str(seeded["warehouse_id"]),
            "lines": [{"product_id": str(seeded["product_ids"]["SKU-1001"]), "quantity": "1", "unit_price": "6200"}],
        },
    )
    assert order.status_code == 201, order.text
    assert order.json()["document_date"] == "2026-04-01"
