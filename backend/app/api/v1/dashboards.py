"""Role dashboards, KPIs and chart series.

Each dashboard is guarded by the permission of the module it summarises, so a
salesperson cannot read the accounting dashboard and vice versa.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import PermissionDeniedError
from app.models.identity import User
from app.services.dashboard_service import DashboardService

router = APIRouter()

DASHBOARD_PERMISSIONS = {
    "management": "core.dashboard.view",
    "sales": "crm.customer.view",
    "purchasing": "purchasing.purchase_order.view",
    "warehouse": "inventory.stock_ledger.view",
    "accounting": "accounting.journal_entry.view",
    "hr": "hr.employee.view",
    "service": "service.ticket.view",
    "projects": "projects.project.view",
    "pos": "sales.pos_shift.view",
}

DASHBOARD_METHODS = {
    "management": "management",
    "sales": "sales",
    "purchasing": "purchasing",
    "warehouse": "warehouse",
    "accounting": "accounting",
    "hr": "hr",
    "service": "service",
    "projects": "projects",
    "pos": "pos",
}


def _guard(current: CurrentUserDep, name: str) -> None:
    """A dashboard needs the shared dashboard permission plus the module's read right."""
    permission = DASHBOARD_PERMISSIONS[name]
    if not current.can("core.dashboard.view") or not current.can(permission):
        raise PermissionDeniedError(f"You do not have access to the {name} dashboard", permission=permission)


def _service(db: DB, current: CurrentUserDep) -> DashboardService:
    return DashboardService(db, current.company_id)


@router.get("", summary="Dashboards the caller may open")
def available(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.dashboard.view")
    items = [
        {"name": name, "permission": permission}
        for name, permission in DASHBOARD_PERMISSIONS.items()
        if current.can(permission)
    ]
    return {"items": items, "total": len(items)}


@router.get("/me", summary="Dashboard matching the caller's permissions")
def my_dashboard(
    db: DB,
    current: CurrentUserDep,
    scope: str = Query("management"),
    salesperson_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    current.require("core.dashboard.view")
    codes = current.permissions.as_sorted_list()
    result = _service(db, current).for_user(codes, scope=scope)
    if scope == "sales" and salesperson_id and current.can("sales.sales_order.approve"):
        return _service(db, current).sales(salesperson_id=salesperson_id)
    if scope == "warehouse":
        return _service(db, current).warehouse(warehouse_id=warehouse_id)
    return result


@router.get("/management", summary="Management dashboard")
def management(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "management")
    return _service(db, current).management()


@router.get("/sales", summary="Sales dashboard")
def sales(
    db: DB, current: CurrentUserDep, salesperson_id: uuid.UUID | None = None
) -> dict[str, Any]:
    _guard(current, "sales")
    scope_to_self = None if current.can("sales.sales_order.view") and current.can("crm.customer.edit") else current.id
    return _service(db, current).sales(salesperson_id=salesperson_id or scope_to_self)


@router.get("/purchasing", summary="Purchasing dashboard")
def purchasing(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "purchasing")
    return _service(db, current).purchasing()


@router.get("/warehouse", summary="Warehouse dashboard")
def warehouse(db: DB, current: CurrentUserDep, warehouse_id: uuid.UUID | None = None) -> dict[str, Any]:
    _guard(current, "warehouse")
    return _service(db, current).warehouse(warehouse_id=warehouse_id)


@router.get("/accounting", summary="Accounting dashboard")
def accounting(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "accounting")
    return _service(db, current).accounting()


@router.get("/hr", summary="HR dashboard")
def hr(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "hr")
    return _service(db, current).hr()


@router.get("/service", summary="Service desk dashboard")
def service(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "service")
    return _service(db, current).service()


@router.get("/projects", summary="Projects dashboard")
def projects(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    _guard(current, "projects")
    return _service(db, current).projects()


@router.get("/pos", summary="Point of sale dashboard")
def pos(db: DB, current: CurrentUserDep, shift_id: uuid.UUID | None = None) -> dict[str, Any]:
    _guard(current, "pos")
    return _service(db, current).pos(shift_id=shift_id)


# --------------------------------------------------------------------------- #
# Cross-module KPI helpers used by the Flutter home page
# --------------------------------------------------------------------------- #
@router.get("/kpis", summary="Headline KPIs for the caller")
def kpis(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.dashboard.view")
    service = _service(db, current)
    payload: dict[str, Any] = {"generated_at": date.today().isoformat(), "cards": []}
    if current.can("crm.customer.view"):
        sales_data = service.sales()
        payload["cards"].append({"key": "sales_month", "value": sales_data.get("month_to_date", "0")})
        payload["sales"] = sales_data
    if current.can("inventory.stock_ledger.view"):
        payload["warehouse"] = service.warehouse()
    if current.can("accounting.journal_entry.view"):
        payload["accounting"] = service.accounting()
    return payload


@router.get("/charts/sales-trend", summary="Daily sales trend series")
def sales_trend(
    db: DB,
    current: CurrentUserDep,
    days: int = Query(30, ge=7, le=365),
) -> dict[str, Any]:
    current.require("crm.customer.view")
    from app.models.sales import SalesInvoice

    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = db.execute(
        select(SalesInvoice.document_date, func.coalesce(func.sum(SalesInvoice.total_amount), 0))
        .where(
            SalesInvoice.company_id == current.company_id,
            SalesInvoice.document_date >= start,
            SalesInvoice.document_date <= today,
            SalesInvoice.status.in_(["approved", "posted"]),
        )
        .group_by(SalesInvoice.document_date)
        .order_by(SalesInvoice.document_date)
    ).all()
    series = {row[0].isoformat(): str(row[1]) for row in rows}
    return {
        "from": start.isoformat(),
        "to": today.isoformat(),
        "labels": [(start + timedelta(days=offset)).isoformat() for offset in range(days)],
        "values": [
            series.get((start + timedelta(days=offset)).isoformat(), "0") for offset in range(days)
        ],
    }


@router.get("/charts/top-products", summary="Best selling products")
def top_products(
    db: DB,
    current: CurrentUserDep,
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    current.require("crm.customer.view")
    from app.models.sales import SalesInvoiceLine

    start = date.today() - timedelta(days=days - 1)
    rows = db.execute(
        select(
            SalesInvoiceLine.product_id,
            func.coalesce(func.sum(SalesInvoiceLine.line_total), 0).label("amount"),
        )
        .where(
            SalesInvoiceLine.company_id == current.company_id,
            SalesInvoiceLine.created_at >= start,
        )
        .group_by(SalesInvoiceLine.product_id)
        .order_by(func.coalesce(func.sum(SalesInvoiceLine.line_total), 0).desc())
        .limit(limit)
    ).all()
    product_ids = [row[0] for row in rows if row[0]]
    names: dict[uuid.UUID, str] = {}
    if product_ids:
        from app.models.masterdata import Product

        names = {
            product_id: f"{code} — {name}"
            for product_id, code, name in db.execute(
                select(Product.id, Product.sku, Product.name).where(Product.id.in_(product_ids))
            ).all()
        }
    return {
        "items": [
            {"product_id": str(row[0]), "label": names.get(row[0], str(row[0])), "amount": str(row[1])}
            for row in rows
        ]
    }


@router.get("/users/headcount", summary="Active user count by role")
def headcount(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.user.view")
    from app.models.identity import Role, UserRole

    rows = db.execute(
        select(Role.code, func.count(UserRole.id))
        .join(UserRole, UserRole.role_id == Role.id)
        .where((Role.company_id == current.company_id) | (Role.company_id.is_(None)))
        .group_by(Role.code)
    ).all()
    total = db.execute(
        select(func.count(User.id)).where(User.company_id == current.company_id, User.status == "active")
    ).scalar_one()
    return {
        "active_users": int(total),
        "by_role": [{"role": row[0], "users": int(row[1])} for row in rows],
    }


__all__ = ["router"]
