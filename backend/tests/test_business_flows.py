"""End-to-end business flows: sales, purchasing, inventory, accounting and reports."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

TODAY = "2026-02-01"


def _create_adjustment(client: TestClient, headers: dict[str, str], seeded: dict, quantity: str = "5") -> dict[str, Any]:
    response = client.post(
        "/api/v1/stock-adjustments",
        headers=headers,
        json={
            "warehouse_id": str(seeded["warehouse_id"]),
            "adjustment_date": TODAY,
            "reason": "pytest adjustment",
            "lines": [
                {
                    "product_id": str(seeded["product_ids"]["SKU-1001"]),
                    "direction": "increase",
                    "quantity": quantity,
                    "unit_cost": "4800",
                }
            ],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_stock_adjustment_posts_to_the_ledger(client: TestClient, admin_headers: dict[str, str], seeded: dict) -> None:
    adjustment = _create_adjustment(client, admin_headers, seeded)
    assert adjustment["status"] == "draft"

    posted = client.post(f"/api/v1/stock-adjustments/{adjustment['id']}/post", headers=admin_headers, json={})
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "posted"

    ledger = client.get(
        f"/api/v1/stock/ledger?product_id={seeded['product_ids']['SKU-1001']}&limit=5", headers=admin_headers
    )
    assert ledger.status_code == 200
    assert any(entry["reference_type"] for entry in ledger.json()["items"])

    balances = client.get("/api/v1/stock/balances", headers=admin_headers)
    assert balances.status_code == 200

    reconcile = client.get("/api/v1/stock/reconcile", headers=admin_headers)
    assert reconcile.status_code == 200
    assert reconcile.json().get("difference") in (0, "0", None, "0.0000", Decimal("0"))

    posted_again = client.post(f"/api/v1/stock-adjustments/{adjustment['id']}/post", headers=admin_headers, json={})
    assert posted_again.status_code in (400, 409, 422)


def test_posted_documents_are_immutable(client: TestClient, admin_headers: dict[str, str], seeded: dict) -> None:
    adjustment = _create_adjustment(client, admin_headers, seeded, quantity="3")
    client.post(f"/api/v1/stock-adjustments/{adjustment['id']}/post", headers=admin_headers, json={})

    edit = client.patch(
        f"/api/v1/stock-adjustments/{adjustment['id']}",
        headers=admin_headers,
        json={"reason": "changed my mind"},
    )
    assert edit.status_code in (400, 409, 422), edit.text

    unpost = client.post(
        f"/api/v1/stock-adjustments/{adjustment['id']}/unpost",
        headers=admin_headers,
        json={"reason": "correction"},
    )
    assert unpost.status_code == 200, unpost.text
    assert unpost.json()["status"] in {"draft", "posted"}


def test_unposting_requires_a_reason(client: TestClient, admin_headers: dict[str, str], seeded: dict) -> None:
    adjustment = _create_adjustment(client, admin_headers, seeded, quantity="1")
    client.post(f"/api/v1/stock-adjustments/{adjustment['id']}/post", headers=admin_headers, json={})
    response = client.post(f"/api/v1/stock-adjustments/{adjustment['id']}/unpost", headers=admin_headers, json={})
    assert response.status_code == 422


def test_sales_order_to_invoice_to_payment(
    client: TestClient, admin_headers: dict[str, str], seeded: dict, customer_id: uuid.UUID
) -> None:
    order = client.post(
        "/api/v1/sales-orders",
        headers=admin_headers,
        json={
            "customer_id": str(customer_id),
            "document_date": TODAY,
            "warehouse_id": str(seeded["warehouse_id"]),
            "lines": [
                {"product_id": str(seeded["product_ids"]["SKU-1001"]), "quantity": "2", "unit_price": "6200"}
            ],
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    assert client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=admin_headers, json={}).status_code == 200
    assert (
        client.post(
            f"/api/v1/sales-orders/{order_id}/approve", headers=admin_headers, json={"allow_credit_override": True}
        ).status_code
        == 200
    )

    delivery = client.post(f"/api/v1/sales-orders/{order_id}/delivery", headers=admin_headers, json={})
    assert delivery.status_code in (200, 201), delivery.text
    delivery_id = delivery.json()["id"]
    assert client.post(f"/api/v1/deliveries/{delivery_id}/post", headers=admin_headers, json={}).status_code == 200

    invoice = client.post(
        f"/api/v1/sales-orders/{order_id}/invoice",
        headers=admin_headers,
        json={"delivery_note_id": delivery_id, "allow_credit_override": True},
    )
    assert invoice.status_code in (200, 201), invoice.text
    invoice_body = invoice.json()
    assert Decimal(str(invoice_body["total_amount"])) > 0

    posted = client.post(f"/api/v1/sales-invoices/{invoice_body['id']}/post", headers=admin_headers, json={})
    assert posted.status_code == 200, posted.text

    detail = client.get(f"/api/v1/sales-invoices/{invoice_body['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["journal_entry_id"]


def test_purchase_order_to_receipt_to_invoice(
    client: TestClient, admin_headers: dict[str, str], seeded: dict, supplier_id: uuid.UUID
) -> None:
    order = client.post(
        "/api/v1/purchase-orders",
        headers=admin_headers,
        json={
            "supplier_id": str(supplier_id),
            "document_date": TODAY,
            "warehouse_id": str(seeded["warehouse_id"]),
            "lines": [
                {"product_id": str(seeded["product_ids"]["SKU-1002"]), "quantity": "1", "unit_price": "12000"}
            ],
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    assert client.post(f"/api/v1/purchase-orders/{order_id}/approve", headers=admin_headers, json={}).status_code == 200

    receipt = client.post(f"/api/v1/purchase-orders/{order_id}/receipt", headers=admin_headers, json={})
    assert receipt.status_code in (200, 201), receipt.text
    receipt_id = receipt.json()["id"]
    assert client.post(f"/api/v1/goods-receipts/{receipt_id}/post", headers=admin_headers, json={}).status_code == 200

    invoice = client.post(
        f"/api/v1/purchase-orders/{order_id}/invoice",
        headers=admin_headers,
        json={"goods_receipt_id": receipt_id},
    )
    assert invoice.status_code in (200, 201), invoice.text
    assert client.post(f"/api/v1/purchase-invoices/{invoice.json()['id']}/post", headers=admin_headers, json={}).status_code == 200


def test_supplier_360_exposes_balance_and_contacts(
    client: TestClient, admin_headers: dict[str, str], supplier_id: uuid.UUID
) -> None:
    response = client.get(f"/api/v1/suppliers/{supplier_id}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "balance" in body and "recent_invoices" in body

    contact = client.post(
        f"/api/v1/suppliers/{supplier_id}/contacts",
        headers=admin_headers,
        json={"first_name": "Nour", "last_name": "Saleh", "email": "nour@example.com"},
    )
    assert contact.status_code == 201, contact.text


def test_financial_reports_balance(client: TestClient, admin_headers: dict[str, str]) -> None:
    trial = client.get("/api/v1/reports/trial-balance?date_from=2026-01-01&date_to=2026-12-31", headers=admin_headers)
    assert trial.status_code == 200, trial.text
    body = trial.json()
    assert Decimal(str(body["totals"]["difference"])) == Decimal("0")
    assert body["rows"]

    balance_sheet = client.get("/api/v1/reports/balance-sheet?as_of=2026-12-31", headers=admin_headers)
    assert balance_sheet.status_code == 200
    assert balance_sheet.json()["rows"]

    income = client.get(
        "/api/v1/reports/income-statement?date_from=2026-01-01&date_to=2026-12-31", headers=admin_headers
    )
    assert income.status_code == 200

    catalogue = client.get("/api/v1/reports/catalogue", headers=admin_headers)
    assert catalogue.status_code == 200
    codes = {item["code"] for item in catalogue.json()["items"]}
    assert {"trial_balance", "balance_sheet", "income_statement"} <= codes


def test_report_export_csv(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/reports/export/trial_balance?file_format=csv",
        headers=admin_headers,
        json={"parameters": {"date_from": "2026-01-01", "date_to": "2026-12-31"}},
    )
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert len(response.content) > 20


def test_saved_report_round_trip(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/reports/saved",
        headers=admin_headers,
        json={
            "code": f"pytest.saved.{uuid.uuid4().hex[:6]}",
            "name": "Pytest saved report",
            "report_type": "custom",
            "definition": {"report_code": "trial_balance", "parameters": {"date_from": "2026-01-01"}},
        },
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    run = client.post(f"/api/v1/reports/saved/{report_id}/run", headers=admin_headers, json={})
    assert run.status_code == 200, run.text

    assert client.delete(f"/api/v1/reports/saved/{report_id}", headers=admin_headers).status_code == 200


def test_dashboards_search_and_notifications(client: TestClient, admin_headers: dict[str, str]) -> None:
    dashboard = client.get("/api/v1/dashboards/management", headers=admin_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["kpis"]

    search = client.get("/api/v1/search?q=SKU-1001", headers=admin_headers)
    assert search.status_code == 200
    assert search.json()["groups"]

    notifications = client.get("/api/v1/notifications", headers=admin_headers)
    assert notifications.status_code == 200
    assert "items" in notifications.json()

    unread = client.get("/api/v1/notifications/unread-count", headers=admin_headers)
    assert unread.status_code == 200


def test_import_preview_reports_invalid_rows(client: TestClient, admin_headers: dict[str, str]) -> None:
    rows = [
        {"name": "Valid Group", "code": f"VG{uuid.uuid4().hex[:5]}"},
        {"name": "", "code": ""},
    ]
    entities = client.get("/api/v1/data-tools/import/entities", headers=admin_headers).json()["items"]
    assert entities
    entity_type = next(
        (item["entity"] for item in entities if "group" in str(item.get("entity", "")).lower()),
        entities[0]["entity"],
    )
    job = client.post(
        "/api/v1/data-tools/import/rows",
        headers=admin_headers,
        json={"entity_type": entity_type, "rows": rows, "file_name": "pytest.csv"},
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    validated = client.post(f"/api/v1/data-tools/import/jobs/{job_id}/validate", headers=admin_headers)
    assert validated.status_code == 200, validated.text
    report = validated.json()
    assert report["invalid_rows"] >= 1, report
    assert report["valid_rows"] >= 1, report
    assert report["error_summary"], "invalid rows must be reported, never silently dropped"

    preview = client.get(f"/api/v1/data-tools/import/jobs/{job_id}/preview", headers=admin_headers)
    assert preview.status_code == 200


def test_backup_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/data-tools/backup", headers=admin_headers, json={"backup_type": "manual"})
    assert created.status_code == 201, created.text
    backup_id = created.json()["id"]

    verified = client.post(f"/api/v1/data-tools/backup/{backup_id}/verify", headers=admin_headers)
    assert verified.status_code == 200
    assert verified.json()["valid"] is True

    instructions = client.get(f"/api/v1/data-tools/backup/{backup_id}/restore-instructions", headers=admin_headers)
    assert instructions.status_code == 200
    assert instructions.json()["steps"]

    listed = client.get("/api/v1/data-tools/backup", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"]


def test_attachment_upload_and_download(client: TestClient, admin_headers: dict[str, str], customer_id: uuid.UUID) -> None:
    upload = client.post(
        "/api/v1/attachments",
        headers=admin_headers,
        data={"entity_type": "customer", "entity_id": str(customer_id), "title": "Pytest contract"},
        files={"files": ("contract.txt", b"Kayan ERP attachment payload", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["items"][0]["id"]

    download = client.get(f"/api/v1/attachments/{attachment_id}/download", headers=admin_headers)
    assert download.status_code == 200
    assert b"Kayan ERP attachment payload" in download.content

    assert client.delete(f"/api/v1/attachments/{attachment_id}", headers=admin_headers).status_code == 200


def test_workflow_definition_and_delegation(client: TestClient, admin_headers: dict[str, str], seeded: dict) -> None:
    definition = client.post(
        "/api/v1/workflow/definitions",
        headers=admin_headers,
        json={
            "code": f"PYTEST-PO-{uuid.uuid4().hex[:5]}",
            "name": "Pytest purchase approvals",
            "document_type": "purchase_order",
            "steps": [{"name": "Manager", "approver_type": "user", "approver_user_id": str(seeded["admin_id"])}],
        },
    )
    assert definition.status_code == 201, definition.text
    definition_id = definition.json()["id"]

    detail = client.get(f"/api/v1/workflow/definitions/{definition_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["steps"]

    delegation = client.post(
        "/api/v1/workflow/delegations",
        headers=admin_headers,
        json={"to_user_id": str(seeded["admin_id"]), "start_date": TODAY, "end_date": "2026-03-01", "reason": "pytest"},
    )
    assert delegation.status_code == 201, delegation.text
    assert client.delete(f"/api/v1/workflow/delegations/{delegation.json()['id']}", headers=admin_headers).status_code == 200


def test_websocket_notification_channel(client: TestClient) -> None:
    login = client.post("/api/v1/auth/login", json={"email": "admin@kayan-demo.com", "password": "Admin@12345"})
    token = login.json()["access_token"]
    with client.websocket_connect(f"/api/v1/ws/notifications?token={token}") as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"


def test_websocket_rejects_invalid_tokens(client: TestClient) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/api/v1/ws/notifications?token=not-a-token"):
            pass
    assert error.value.code == 4401
