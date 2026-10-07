# Kayan ERP

**Kayan ERP** is a universal, multi-tenant ERP platform: one backend, one web client and
one permission model covering sales, purchasing, inventory, accounting, cash and banks,
fixed assets, expenses, projects, HR and payroll, manufacturing, service and POS.

It is built as a production system, not a prototype: real double-entry accounting, an
immutable stock ledger, tenant isolation enforced in the database session, a server-side
permission catalogue of 1113 codes, document lifecycles where posted records can only be
corrected by reversal, and an automated test suite that exercises the money paths end to end.

```
Flutter (Material 3, AR/EN) ──HTTP/JSON──► FastAPI ──SQLAlchemy──► PostgreSQL
        │                                     │
        └──────────── WebSocket ──────────────┘ (notifications, presence)
```

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic |
| Database | PostgreSQL 16 (SQLite for tests and local smoke runs) |
| Frontend | Flutter 3 (web + desktop), Material 3, Riverpod, GoRouter, Dio, fl_chart |
| Auth | JWT access + refresh tokens, Bcrypt, session/device tracking, revocation |
| Infra | Docker, Docker Compose, Nginx, GitHub Actions |

## Quick start

```bash
# 1. configuration
cp infrastructure/.env.example .env
#    edit POSTGRES_PASSWORD, SECRET_KEY, CORS_ORIGINS

# 2. run the stack (PostgreSQL + API + Nginx + Flutter web)
docker compose -f infrastructure/docker-compose.yml up --build
```

| Surface | URL |
| --- | --- |
| REST API | http://localhost:8080/api/v1 |
| OpenAPI + Swagger | http://localhost:8080/docs |
| Health probe | http://localhost:8080/health |
| Web client | http://localhost:8080 |

Without Docker, see [docs/development.md](docs/development.md).

## Demo credentials (development seed only)

Started with `SEED_DEMO_DATA=true` in a non-production environment, the API seeds a demo
company with branches, warehouses, products, customers, suppliers and sample transactions:

| User | Password | Role |
| --- | --- | --- |
| `admin@kayan-demo.com` | `Admin@12345` | Company administrator |
| `manager@kayan-demo.com` | `Admin@12345` | General manager |
| `sales@kayan-demo.com` | `Admin@12345` | Sales representative |
| `store@kayan-demo.com` | `Admin@12345` | Warehouse clerk |
| `accountant@kayan-demo.com` | `Admin@12345` | Accountant |
| `cashier@kayan-demo.com` | `Cashier@12345` | POS cashier |

> These credentials are development fixtures. Production deployments must never enable the
> demo seed; create the first administrator with `BOOTSTRAP_ADMIN_EMAIL` /
> `BOOTSTRAP_ADMIN_PASSWORD` and rotate the password on first login.

## Repository layout

```
backend/          FastAPI application (domain, services, repositories, routes, schemas)
  app/core/       config, database session and tenant scope, security, permissions, errors
  app/models/     195 mapped tables grouped by module
  app/services/   31 services holding all business logic
  app/api/v1/     24 routers exposing 715 documented paths
  tests/          pytest suite (platform + business flows)
  alembic/        schema migrations
frontend/         Flutter client (feature-first, resource + document engines)
infrastructure/   docker-compose.yml, nginx.conf, Dockerfiles, .env.example
docs/             architecture, database, api, permissions, modules, deployment, testing
.github/          CI workflow (backend lint/test, Flutter analyze/test/build, image build)
```

## Documentation

| Document | Contents |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Layers, multi-tenancy, document lifecycle, frontend engines |
| [docs/database.md](docs/database.md) | Tables, keys, constraints, indexes, migrations |
| [docs/api.md](docs/api.md) | Authentication, error codes, pagination, endpoints, WebSocket |
| [docs/permissions.md](docs/permissions.md) | Permission catalogue, role templates, data scope |
| [docs/modules.md](docs/modules.md) | Every business module and its documents |
| [docs/deployment.md](docs/deployment.md) | Docker, Nginx, environment variables, production checklist |
| [docs/development.md](docs/development.md) | Local setup, code style, adding a module |
| [docs/testing.md](docs/testing.md) | Automated suites, smoke checks, manual QA |

## Status

Implemented and covered by automated tests: platform core (companies, branches,
departments, users, roles, permissions, settings, numbering, audit), master data, CRM,
suppliers, item master, inventory, purchasing, sales, POS, accounting, cash and banks,
taxes, fixed assets, expenses, projects, HR, payroll, manufacturing, service, workflow,
notifications, attachments, reports, dashboards, search, import/export and backup.

Known gaps are tracked in [docs/testing.md](docs/testing.md#known-gaps).
