# Architecture

## 1. Shape of the system

Kayan ERP is a three-tier application with a single API surface shared by the web client,
desktop builds and any future integration:

```
┌──────────────────────────── Flutter client ─────────────────────────────┐
│ presentation  features/<domain>/presentation  (screens, no business logic)│
│ state         Riverpod controllers + providers                            │
│ engines       shared/resource  (CRUD)   shared/resource  (documents)      │
│ transport     core/network (Dio) + core/repository (KayanApi)             │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │ HTTPS/JSON + WebSocket
┌──────────────────────────────────▼────────────────────────────────────────┐
│ FastAPI                                                                   │
│  api/v1/*        routers: parse, authorise, delegate, serialise            │
│  api/deps.py     DB session, CurrentUser, permission guard, audit context │
│  services/*      31 services: all business rules, transactions, posting    │
│  models/*        195 tables, UUID keys, audit columns, tenant column       │
│  core/*          config, database scope, security, permissions, pagination │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │ SQLAlchemy 2.0
                             PostgreSQL 16
```

Hard rules kept by the codebase:

* **No business logic in routes.** Routers validate input, check permissions and call one
  service method; every calculation, state transition and posting lives in a service.
* **No SQL and no business logic in widgets.** The Flutter client speaks only to
  `KayanApi`, which speaks only to the versioned REST surface.
* **Posted documents are immutable.** Editing happens through reversal (unpost) and a new
  document, never by mutation.
* **Multi-step operations are one transaction.** A delivery + stock movement + accounting
  entry commit together or not at all (`session.begin()` in the service layer).

## 2. Backend layers

| Layer | Location | Responsibility |
| --- | --- | --- |
| Config | `app/core/config.py` | Environment driven settings, validated at import |
| Database | `app/core/database.py` | Engine/session, `CompanyScoped` mixin, tenant filter, `session_scope`, naive-UTC helpers |
| Security | `app/core/security.py` | Password hashing (Bcrypt), JWT encode/decode, ticket tokens |
| Permissions | `app/core/permissions.py` | Catalogue of 16 modules / 159 entities / 1113 actions, role templates, data scope |
| Errors | `app/core/errors.py` | Typed errors with stable `code` values and a single JSON envelope |
| Repository | `app/core/repository.py` | Generic list/get/create/update/soft-delete helpers |
| Pagination | `app/core/pagination.py` | `PageParams` parsing and `{items,total,page,page_size,pages}` serialisation |
| CRUD factory | `app/api/crud.py` | `ResourceSpec` + `build_crud_router` produce a consistent, permission guarded CRUD router |
| Document engine | `app/api/documents.py` + `app/services/document_service.py` | Lifecycle transitions, workflow hooks, numbering, posting |
| Services | `app/services/*` | Domain logic per module; the only place that writes business data |

### Request lifecycle

1. `RequestContextMiddleware` assigns `X-Request-Id`, measures `X-Process-Time-Ms` and
   applies rate limiting.
2. `api/deps.py::get_current_user` decodes the bearer token, loads the session and the
   user's permission set for the active company, and rejects revoked or expired sessions.
3. The route calls `current.require("module.entity.action")`; unknown or missing codes
   raise `PermissionDeniedError` (403 `permission_denied`).
4. The service performs the work inside a transaction, writes audit entries through
   `AuditService`, and returns domain objects.
5. The route serialises with `json_safe` so `Decimal`/`date`/`UUID` survive JSON encoding.

Errors are always:

```json
{ "code": "validation_error", "message": "Quantity must be positive", "details": {} }
```

`code` is stable and translated by the Flutter client (`error.validation`, `error.not_found`,
`error.permission_denied`, `error.conflict`, `error.business_rule`, `error.rate_limited`,
`error.unknown`).

## 3. Multi-tenancy

Every business table inherits `CompanyScoped`, which provides `company_id`. A tenant filter
is installed on the SQLAlchemy session:

* `session_scope(company_id)` sets the active company; `with_loader_criteria` then appends
  `company_id = :active_company` to every query that touches a `CompanyScoped` entity.
* The filter is applied server side, never based on a client supplied header alone: the
  company comes from the authenticated session and is validated against the user's company
  membership on every request.
* `skip_tenant()` is used only inside deliberately global operations (seeding, migrations,
  platform administration) and is always narrowly scoped.

Organization hierarchy: `company → branch → department → division → cost centre → warehouse`,
with users assigned to branches/warehouses and roles carrying a data scope
(`company`, `branch`, `warehouse`, `own`, `team`) that narrows list queries.

## 4. Document lifecycle

Business documents (quotation, order, delivery, invoice, receipt, payment, journal entry,
production order, work order, …) share one engine:

```
draft ──submit──► submitted ──approve──► approved ──post──► posted
  ▲                   │                     │                │
  │                   └────reject───────────┘                └──unpost──► posted (reversed)
  └────────────────────────────── cancel ────────────────────────────────┘
```

* `EDITABLE_STATUSES = {draft, rejected}` — anything else is read only.
* `BaseDocumentService` provides `get_document`, `list_documents`, `update`,
  `delete_draft`, `ensure_editable`, `transition`, `submit`, `approve`, `reject`, `post`,
  `unpost`, `cancel`, plus the hooks `validate_posting`, `after_post`, `after_unpost`,
  `apply_totals`, `apply_inventory`, `reverse_inventory`.
* `build_document_router(DocumentSpec(...))` exposes the standard routes:
  `GET/POST /{collection}`, `GET/PATCH/DELETE /{collection}/{id}`,
  `POST /{collection}/{id}/{action}` for `submit|approve|reject|post|unpost|cancel`,
  plus any `extra_routes` (for example `POST /payments/{id}/allocate`).
* Numbering is allocated inside the caller's transaction (`NumberingService.next_number`)
  so gaps and duplicates cannot appear under concurrency.
* Rejection and unposting require a reason; the reason is written to the audit log.

### Cross-module side effects

Posting delegates the financial and stock consequences to dedicated services, all inside the
same transaction:

| Effect | Service |
| --- | --- |
| Ledger entries | `PostingService` (account resolution by role, dimension aware) |
| Stock movements | `StockLedgerService` / `stock_operations_service` (append-only ledger) |
| Cash and bank | `TreasuryService` |
| Costing | `CostingService` (moving average and WIP) |
| Commissions | `CommissionService` |
| Notifications | `NotificationService` (in-app row + WebSocket push) |
| Workflow | `WorkflowService` (amount-tiered steps, delegation, timeout actions) |

## 5. Frontend architecture

```
lib/
  main.dart            bootstrap: session restore, date symbols, runApp
  app.dart             MaterialApp.router: theme, locale (ar/en), RTL direction
  core/
    config/            dart-define driven configuration (API_BASE_URL, page sizes)
    l10n/              327 English + 327 Arabic keys, context.tr / trp / isRtl
    network/           Dio client: bearer header, refresh-on-401, error mapping
    repository/        KayanApi: typed access to every endpoint family
    storage/           SessionStore (shared preferences) for tokens and preferences
    models/            AuthState, CurrentUser, CompanyRef, RoleRef, PagedResult
    providers.dart     apiProvider, authProvider, localeProvider, themeModeProvider
    router/            GoRouter with auth redirect and module permission guard
    theme/             Material 3 light/dark from a single seed colour
  shared/
    widgets/           async/empty/error states, page header, KPI card, table, forms, dialogs
    resource/          ResourceConfig + DocumentConfig engines, providers, pages
  features/
    modules/           76 resource configs, 28 document configs, navigation groups
    auth/ dashboard/ pos/ reports/ settings/ data_tools/ notifications/ shell/
```

* **Resource engine** — a `ResourceConfig` describes path, permissions, columns, fields,
  filters and export entity. `ResourcePage` renders the list, filters, pagination, create
  and edit dialogs, delete confirmation and export, so a new master-data screen is a
  declaration rather than a screen.
* **Document engine** — a `DocumentConfig` adds header fields, line fields, statuses,
  totals and lifecycle actions. `DocumentPage` renders the list, the detail dialog
  (header, lines, totals, attachments, audit timeline) and the standard actions filtered by
  status and permission.
* **No hardcoded UI text** — every label is a localisation key; Arabic renders RTL through a
  single `Directionality` wrapper, and numbers/currency/dates go through `Fmt` +
  `intl` with Arabic formatting (`ar` locale, Arabic month names).
* **Security is not a UI concern** — the client hides what the user cannot use, but every
  call is authorised again on the server.

Realtime: the client opens `WS /ws/notifications` with the access token; the server pushes
`unread` counters and notification payloads, closing with `4401` (unauthorized) or
`4403` (forbidden) when the token or permission set no longer allows the channel.

## 6. Extension points

| Need | Where to extend |
| --- | --- |
| New master data screen | `frontend/lib/features/modules/*_configs.dart` (declaration only) |
| New document type | Model + service subclass of `BaseDocumentService` + `DocumentSpec` + a `DocumentConfig` |
| New report | Register in `report_service.REPORTS`, then it appears in `/reports/catalogue` and the client |
| New approval rule | `workflow` tables (`WorkflowDefinition`, `WorkflowStep`, `ConditionTemplate`) — no code change |
| New tax rule | Per-company tax configuration in master data, consumed by `TaxEngine` |
| New payroll component | `SalaryComponent` rows with formula, scope and taxable flags |
| New channel (SMS/push/WhatsApp) | Adapter behind `NotificationService` dispatch |
| New import entity | `ENTITY_DEFINITIONS` in `import_export_service` |
