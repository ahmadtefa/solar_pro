# Development

## 1. Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Python | 3.11+ | Backend |
| PostgreSQL | 16 (optional) | Realistic local runs; SQLite works for tests |
| Flutter | 3.22+ (stable) | Web and desktop client |
| Docker + Compose | 24+ | Full stack |
| Node | 20+ | Only if you extend the CI helpers |

## 2. Backend setup

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                      # set DATABASE_URL and SECRET_KEY
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

* Swagger UI: http://localhost:8000/docs
* The development seed runs when `SEED_DEMO_DATA=true` and the environment is not
  `production`; it creates the demo company, users, products, customers, suppliers and a few
  sample transactions so the dashboards are not empty.
* SQLite is the default so a first run needs no database server; switch to
  `postgresql+psycopg://user:pass@localhost:5432/kayan` for parity with production.

### Layout

```
app/
  core/        config, database + tenant scope, security, permissions, errors, pagination,
               repository, rate limiting, coercion helpers, enums, json utilities
  models/      one module per file, imported by models/__init__.py (195 tables)
  schemas/     Pydantic v2 contracts (auth, master data, common envelopes)
  services/    31 services — all business logic lives here
  api/
    deps.py    session, CurrentUser, permission guard, audit context
    crud.py    ResourceSpec + build_crud_router
    documents.py  DocumentSpec + lifecycle routes
    exports.py    CSV/XLSX/PDF/binary response helpers
    v1/        24 routers
alembic/       migrations
tests/         pytest suite
```

### Code style

* `ruff` with a 110 column limit and the `E,F,W,I,B,C4,UP,S` rule families:
  `.venv/bin/ruff check app tests` must pass, and imports must be sorted.
* Type hints on public functions; `from __future__ import annotations` at the top of modules.
* Services raise the typed errors from `app/core/errors.py`; never `HTTPException` inside a
  service, never a raw `Exception` from a route.
* No business logic in routes: validate, authorise, call one service method, serialise.

## 3. Frontend setup

```bash
cd frontend
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000/api/v1
flutter build web --release --dart-define=API_BASE_URL=/api/v1   # production build
flutter analyze && flutter test
```

* `API_BASE_URL` defaults to the relative `/api/v1`, which is what the Nginx edge expects.
* The client keeps the access/refresh tokens in `shared_preferences` through `SessionStore`
  and refreshes transparently on a 401.
* Arabic is the RTL locale; every user-visible string lives in
  `lib/core/l10n/app_strings.dart` (English and Arabic maps must stay the same size — a test
  enforces it).

### Adding a master data screen

1. Add the resource to `lib/features/modules/platform_configs.dart` or
   `business_configs.dart`: path, permission prefix, columns, fields, filters.
2. Add it to a navigation group in `module_registry.dart` (the registry check test will tell
   you if a route or permission is inconsistent).
3. Nothing else — the resource page, filters, pagination, form dialog, export and permission
   gating are provided by `shared/resource`.

### Adding a document

1. Model + service: subclass `BaseDocumentService`, implement the hooks you need
   (`apply_totals`, `validate_posting`, `after_post`, …).
2. Router: `build_document_router(DocumentSpec(name="…", service_cls=…, permission_module=…,
   permission_entity=…))`, then mount it in `app/main.py`.
3. Permission catalogue: add the entity and its actions to `app/core/permissions.py`, and
   grant them in the relevant role templates.
4. Tests: extend `tests/test_business_flows.py` with the new flow.
5. Client: add a `DocumentConfig` in `lib/features/modules/document_configs.dart`.
6. Run `.venv/bin/python /tmp/permcheck.py`-style checks (or the test suite) to confirm every
   permission referenced by a router exists in the catalogue.

## 4. Git workflow

* Commit prefixes mirror the modules: `feat(core)`, `feat(auth)`, `feat(rbac)`, `feat(inventory)`,
  `feat(sales)`, `feat(accounting)`, `fix(api)`, `chore(ci)`, `test(backend)`.
* Keep a commit focused on one module or concern; never commit `backend/.env`, `storage/`,
  `backups/`, generated Flutter build output or a real secret.
* Before pushing: `ruff check app tests`, `pytest -q`, `flutter analyze`, `flutter test`.

## 5. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `permission_denied` on a route you just added | The code is missing from `CATALOGUE` — unknown codes are denied by design |
| `can't compare offset-naive and offset-aware datetimes` on SQLite | Use `utcnow_naive()` / `is_past()` / `seconds_until()` for values loaded from the database |
| Dates arrive as strings from JSON | They are normalised by `app/core/coercion.py::normalise_payload` on document routes |
| Migration fails on a SQLite run | Batch mode is required (`render_as_batch=True`, already set in `alembic/env.py`) |
| Flutter shows the login screen after a reload | The stored session was revoked or the refresh token expired — expected |
| `403` in the browser but `200` in curl | CORS: set `CORS_ORIGINS` to the exact origin of the web build |
