"""Kayan ERP application factory.

The FastAPI app is assembled here: middleware, error mapping, the versioned
router mount, health probes and the WebSocket channel used for live
notifications.  Business logic lives in ``app.services``; routers only validate,
authorise and delegate.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import (
    accounting,
    admin,
    assets,
    attachments,
    auth,
    crm,
    dashboards,
    data_tools,
    expenses,
    hr,
    inventory,
    manufacturing,
    masterdata,
    notifications,
    projects,
    purchasing,
    reports,
    sales,
    search,
    service,
    treasury,
    workflow,
    ws,
)
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.errors import register_exception_handlers
from app.core.ratelimit import RateLimitMiddleware

logger = logging.getLogger("kayan")

#: (module, prefix, tag) for every mounted router.  Order matters only for
#: documentation readability; paths are unique by construction.
ROUTERS: tuple[tuple[Any, str, str], ...] = (
    (auth, "", "Authentication"),
    (admin, "/admin", "Platform administration"),
    (masterdata, "", "Master data"),
    (inventory, "", "Inventory"),
    (crm, "", "CRM"),
    (sales, "", "Sales"),
    (purchasing, "", "Purchasing"),
    (accounting, "", "Accounting"),
    (treasury, "", "Cash and banks"),
    (expenses, "", "Expenses"),
    (assets, "", "Fixed assets"),
    (hr, "", "Human resources"),
    (manufacturing, "", "Manufacturing"),
    (projects, "", "Projects"),
    (service, "", "Service"),
    (workflow, "/workflow", "Workflow"),
    (notifications, "/notifications", "Notifications"),
    (attachments, "/attachments", "Attachments"),
    (reports, "/reports", "Reports"),
    (dashboards, "/dashboards", "Dashboards"),
    (search, "/search", "Search"),
    (data_tools, "/data-tools", "Import, export and backup"),
    (ws, "", "Realtime"),
)

TAGS_METADATA = [
    {"name": "Authentication", "description": "Login, refresh, sessions and self service"},
    {"name": "Platform administration", "description": "Companies, module activation, users, roles and audit"},
    {"name": "Master data", "description": "Organisation structure, currencies, taxes, units and fiscal calendar"},
    {"name": "Inventory", "description": "Warehouses, items, stock ledger, movements and stocktaking"},
    {"name": "CRM", "description": "Leads, opportunities, customers, contacts and activities"},
    {"name": "Sales", "description": "Quotations, orders, deliveries, invoices, POS and commissions"},
    {"name": "Purchasing", "description": "Requests, RFQs, orders, receipts, invoices and supplier data"},
    {"name": "Accounting", "description": "Chart of accounts, journals, posting and financial reports"},
    {"name": "Cash and banks", "description": "Cash boxes, bank accounts, cheques and reconciliation"},
    {"name": "Expenses", "description": "Expense categories, claims, advances and budgets"},
    {"name": "Fixed assets", "description": "Asset register, depreciation, transfer and disposal"},
    {"name": "Human resources", "description": "Employees, contracts, attendance, leave and payroll"},
    {"name": "Manufacturing", "description": "BOMs, routings, work centres and production orders"},
    {"name": "Projects", "description": "Projects, tasks, timesheets, billing and profitability"},
    {"name": "Service", "description": "Service requests, tickets, work orders, contracts and warranty"},
    {"name": "Workflow", "description": "Approval definitions, instances and delegations"},
    {"name": "Notifications", "description": "Notification centre, preferences and outbound queue"},
    {"name": "Attachments", "description": "Secure document upload and download"},
    {"name": "Reports", "description": "Report catalogue, saved reports and exports"},
    {"name": "Dashboards", "description": "Role dashboards and KPI series"},
    {"name": "Search", "description": "Global search across the tenant"},
    {"name": "Import, export and backup", "description": "Bulk data tools and backup management"},
    {"name": "Realtime", "description": "WebSocket channels"},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s %s (%s)", settings.app_name, settings.app_version, settings.environment)
    if settings.seed_demo_data and not settings.is_production:
        from app.services.seed_service import SeedService

        with SessionLocal() as session:
            try:
                if not SeedService(session).company_exists():
                    SeedService(session).create_demo_company()
                    session.commit()
                    logger.info("Demo company seeded")
            except Exception:
                session.rollback()
                logger.exception("Demo seeding failed")
    yield
    engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Universal multi-tenant ERP platform: inventory, sales, purchasing, accounting, "
            "treasury, assets, HR and payroll, manufacturing, projects, service, POS, workflow, "
            "notifications and reporting."
        ),
        openapi_url=settings.openapi_url if not settings.is_production else None,
        docs_url=settings.docs_url if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_tags=TAGS_METADATA,
        root_path=settings.root_path,
        lifespan=lifespan,
        contact={"name": "Kayan ERP", "url": "https://github.com/ahmadtefa/Kayan_ERP"},
    )

    _configure_cors(app)
    app.add_middleware(RateLimitMiddleware)
    _register_middleware(app)
    _register_exception_handlers(app)
    _register_health(app)
    _register_routers(app)
    app.openapi = _custom_openapi(app)  # type: ignore[method-assign]
    return app


def _configure_cors(app: FastAPI) -> None:
    origins = settings.cors_origins
    allow_origins = ["*"] if origins.strip() == "*" else [item.strip() for item in origins.split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=settings.cors_allow_credentials and allow_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "X-RateLimit-Remaining", "Content-Disposition"],
    )


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        if response.status_code >= 500:
            logger.error(
                "request failed",
                extra={"path": request.url.path, "request_id": request_id, "status": response.status_code},
            )
        return response


def _register_exception_handlers(app: FastAPI) -> None:
    """Service-layer errors become HTTP responses; unexpected ones get logged."""
    register_exception_handlers(app)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        content: dict[str, Any] = {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None),
        }
        if settings.debug:
            content["details"] = {"type": exc.__class__.__name__, "message": str(exc)}
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)


def _register_health(app: FastAPI) -> None:
    @app.get("/health", tags=["Health"], summary="Liveness probe")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "time": time.time(),
        }

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe (database round trip)")
    def ready() -> JSONResponse:
        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - depends on infrastructure
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "database": "error", "message": str(exc)},
            )
        return JSONResponse(
            content={
                "status": "ready",
                "database": "ok",
                "dialect": engine.dialect.name,
                "version": settings.app_version,
            }
        )

    @app.get("/", tags=["Health"], summary="Service metadata")
    def root() -> dict[str, Any]:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "api": "/api/v1",
            "docs": settings.docs_url if not settings.is_production else None,
            "health": "/health",
        }

    @app.get("/api/v1/version", tags=["Health"], summary="API version and enabled modules")
    def version() -> dict[str, Any]:
        from app.models.platform import DEFAULT_MODULES

        return {
            "version": settings.app_version,
            "api_version": "v1",
            "modules": list(DEFAULT_MODULES),
            "multi_tenant": True,
        }


def _register_routers(app: FastAPI) -> None:
    api_prefix = "/api/v1"
    for module, prefix, tag in ROUTERS:
        app.include_router(module.router, prefix=f"{api_prefix}{prefix}", tags=[tag])


def _custom_openapi(app: FastAPI):
    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        schema["security"] = [{"BearerAuth": []}]
        schema["servers"] = [{"url": "/", "description": "Current deployment"}]
        app.openapi_schema = schema
        return schema

    return openapi


app = create_app()
