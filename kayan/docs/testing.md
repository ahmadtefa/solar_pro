# Testing and verification

## 1. Backend suite (28 tests)

```bash
cd backend
.venv/bin/python -m pytest -q                    # 28 passed
.venv/bin/python -m pytest -q -k invoice         # single area
.venv/bin/ruff check app tests                   # lint
```

`tests/conftest.py` configures the environment **before** importing the application
(`DATABASE_URL=sqlite:///…`, `SECRET_KEY`, `RATE_LIMIT_ENABLED=false`, `STORAGE_DIR`,
`BACKUP_DIR`) and exposes the fixtures `client`, `admin_headers`, `cashier_headers`,
`accountant_headers`, `seeded` (demo company + opening stock + sample transactions),
`customer_id` and `supplier_id`. Every test therefore runs against a real application
instance, a real database schema and real permissions — no mocks on the money paths.

`tests/test_platform.py` (12 tests)

| Area | What is asserted |
| --- | --- |
| Health and metadata | `/health`, `/health/ready`, `/`, `/api/v1/version` respond and report the version |
| OpenAPI | More than 500 documented paths, bearer security scheme present |
| Authentication | Login returns tokens + permission list; refresh rotates; `/auth/me` shape; logout revokes (the old token then gets 401) |
| Authorisation | Cashier and accountant users receive 403 on routes their role does not cover |
| Permission catalogue | Every permission code referenced by any router exists in `CATALOGUE` (regex scan over the source) |
| Role templates | Each template's patterns resolve to existing catalogue codes |
| Tenant isolation | A second company's rows are invisible to the first company's user |
| Date coercion | ISO strings arriving in JSON are coerced for document payloads |
| Realtime | The notification socket rejects an unauthenticated handshake (4401) and accepts a valid token |

`tests/test_business_flows.py` (16 tests)

| Flow | What is asserted |
| --- | --- |
| Sales order → delivery → invoice | Quantities and totals flow through, delivery posts stock, invoice posts AR/revenue, links are kept |
| Purchase order → receipt → invoice | Approval gate, goods receipt stocks, invoice posts AP |
| Double posting | A second `post` returns `conflict` — no doubled ledger entries |
| Posted immutability | `PATCH` on a posted document is refused |
| Unpost | Requires a `reason`, reverses the ledger, returns the document to a correctable state |
| Trial balance / balance sheet / income statement | `totals["difference"] == 0` and the statements tie to the posted flows |
| CSV export | Export endpoint returns the expected headers and rows |
| Saved reports | Create, list and run a saved report definition |
| Dashboards | Role dashboard payload contains KPIs for the seeded company |
| Global search | Search groups results by entity and respects permissions |
| Notifications | Unread counter increments and mark-as-read works |
| Import preview | Valid rows and rejected rows are reported separately (nothing silently dropped) |
| Backup | Create, verify (`valid == true`) and instructions |
| Attachments | Upload, list and authorised download of a stored file |
| Workflow delegation | A delegated approver can decide a step while the original cannot |
| WebSocket | Authenticated socket receives the initial unread frame |

## 2. Frontend tests (13 tests)

```bash
cd frontend
flutter analyze                 # must be clean (strict lints in analysis_options.yaml)
flutter test                    # 13 passed
flutter build web --release --dart-define=API_BASE_URL=/api/v1   # build validation
```

| Suite | Tests | What is asserted |
| --- | --- | --- |
| `test/localization_test.dart` | 5 | English and Arabic key sets are identical (327 each), no empty values, identical placeholder counts, Arabic is RTL and English LTR, placeholder substitution works |
| `test/module_registry_test.dart` | 3 | Every resource config is consistent (absolute path, `module.entity` permissions, unique field keys, fields present when creation is allowed); every document config declares columns/header fields/statuses; navigation groups reference existing configs with unique routes |
| `test/formatters_test.dart` | 5 | Money/quantity parsing from API strings, invalid values returned untouched, ISO date normalisation, status-key mapping, date ranges |

## 3. Static and smoke verification used during development

These are the checks that were run repeatedly while building the modules; they are cheap and
worth scripting again after any change:

| Check | Command | Expected |
| --- | --- | --- |
| HTTP smoke over the whole API | `python /tmp/http_smoke.py` (seed your own DB first) | 65 checks, 0 failures |
| Inventory ↔ GL reconciliation | integration smoke | stock value equals the inventory GL balance (`1368645.00`), AR matches the ledger (`127605.00`) |
| HR + fixed assets | `python /tmp/smoke_hr_assets.py` | payroll and depreciation post with zero variance |
| Manufacturing | `python /tmp/smoke_manufacturing.py` | WIP `39296.00`, scrap valued `2764.00` |
| Projects | `python /tmp/smoke_projects.py` | project cost `340956.25`, margins consistent |
| Service | `python /tmp/smoke_service.py` | work order total `17700.00` |
| Import/export | `python /tmp/smoke_data_tools.py` | 3 rows imported, 2 rejected with reasons |
| Stock operations | `python /tmp/smoke_stock.py` | GL `1310` equals `1112500.00` after transfers/counts |
| Permission references | `python /tmp/permcheck.py` | 407 router references all resolve against 1113 codes |
| Schema build | `alembic upgrade head` on an empty database | 195 tables created |

## 4. Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | Steps |
| --- | --- |
| `backend` | Python 3.11, install `requirements.txt`, `ruff check app tests`, `ruff format --check app tests`, `pytest -q` |
| `frontend` | Flutter stable, `flutter pub get`, `dart format --set-exit-if-changed lib test`, `flutter analyze`, `flutter test`, `flutter build web --release` |
| `docker` | `docker build` for the API image and the web image (validates both Dockerfiles) |

A red job blocks the pull request; there is no "allowed to fail" job.

## 5. Manual QA checklist

Before a release, walk these in the browser:

1. Login as `admin@kayan-demo.com`, switch company, reload — the session survives without a
   second login.
2. Dashboard KPIs match the reports they summarise (sales, receivables, stock value, cash).
3. Create a quotation, convert it to an order, confirm, deliver, invoice, post, then print —
   every step must move status, stock and the ledger.
4. Try to edit a posted invoice: the UI must not offer it, and the API must refuse with a
   reason-required message if attempted directly.
5. Open the POS as `cashier@kayan-demo.com`, open a shift, sell an item, take cash, do a
   cash-in and a return, close the shift with a counted amount and check the difference.
6. Import a CSV with one invalid row — the preview must show it with a reason, and the valid
   rows must import.
7. Run the trial balance and the balance sheet for the current period — the difference must
   be zero.
8. Open the same URL in Arabic: everything must be RTL, translated and numerically formatted.

## 6. Known gaps

* The Flutter client has been verified statically (import graph, structural checks, key
  parity) but not compiled in the development sandbox, which has no Dart/Flutter SDK —
  `flutter analyze`, `flutter test` and the web build run in CI instead.
* Docker Compose and PostgreSQL are configured and documented, but the container stack was
  not started in the development sandbox (no Docker daemon); CI builds the images and the
  migration path is verified against an empty database.
* Import/export ships with three entity definitions (customers, suppliers, products); the
  engine is generic, so more entities are configuration rather than new code.
* Bootstrap provisions the chart of accounts used by the seeded flows; a handful of optional
  accounts (`1420`, `1430`, `2140`, `4220`, `9999`) are only created when a company chooses
  the extended template.
* `GET /admin/bootstrap/status` is a thin shim over the provisioning service and has no
  dedicated test yet.
