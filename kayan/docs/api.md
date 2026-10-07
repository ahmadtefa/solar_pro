# API reference

* **Base URL** — `https://<host>/api/v1` (the Flutter client defaults to the relative
  `/api/v1` so web builds work behind Nginx without CORS).
* **Format** — JSON requests and responses, UTF-8. Binary artefacts are served by the
  download ticket endpoints described in §6.
* **OpenAPI** — `/openapi.json` (schema) and `/docs` (Swagger UI). The current schema
  documents **715 paths**, 256 of them without parameters, mounted from 24 routers.

## 1. Health and metadata

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe (no authentication) |
| GET | `/health/ready` | Readiness probe with a database round trip |
| GET | `/` | Service name, version, environment |
| GET | `/api/v1/version` | API version plus the modules enabled for the caller |

## 2. Authentication

```bash
curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@kayan-demo.com","password":"Admin@12345"}'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "session_id": "...",
  "company_id": "...",
  "permissions": ["core.company.view", "..."],
  "must_change_password": false
}
```

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/auth/login` | Returns tokens, session id, active company and the permission list; locks the account for 15 minutes after 5 failed attempts |
| POST | `/auth/refresh` | Rotates the refresh token, returns a new access token and permission set |
| POST | `/auth/logout` | Revokes the session (and optionally every session of the user) |
| GET | `/auth/me` | User, company, companies, roles, permissions, branches, warehouses, enabled modules, data scope, session id |
| POST | `/auth/switch-company` | Switches the active company when the user has access to several |
| POST | `/auth/change-password` | Requires the current password; honours `password_min_length` |
| POST | `/auth/forgot-password` | Issues a reset token (never reveals whether the address exists) |
| POST | `/auth/reset-password` | Consumes the reset token |
| GET | `/auth/sessions` | Active and revoked devices of the current user |
| DELETE | `/auth/sessions/{id}` | Revokes one session |
| GET | `/auth/permissions` | Permission catalogue grouped by module |
| GET/POST | `/users`, `PATCH /users/{id}` | User administration |
| POST/DELETE | `/users/{id}/roles/{role_id}` | Role assignment |
| POST | `/users/{id}/reset-password` | Administrator initiated reset |
| GET/POST/PATCH | `/roles`, `PUT /roles/{id}/permissions` | Role administration |
| GET | `/audit-logs` | Filterable audit trail |

Authenticate every other call with `Authorization: Bearer <access_token>`. Access tokens
expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60), refresh tokens after
`REFRESH_TOKEN_EXPIRE_DAYS` (default 14). Tokens are bound to their session, and the
permission version of the user is embedded, so a revocation takes effect on the next call.

## 3. Errors

```json
{ "code": "permission_denied", "message": "Missing permission sales.invoice.post", "details": {} }
```

| HTTP | `code` | Meaning |
| --- | --- | --- |
| 400 | `bad_request` | Malformed request |
| 401 | `unauthenticated` | Missing, expired or revoked token |
| 403 | `permission_denied` | Authenticated but not allowed (also used for wrong tenant) |
| 404 | `not_found` | Unknown id or a record outside the caller's company |
| 409 | `conflict` | Duplicate key, already posted, already numbered |
| 422 | `validation_error` | Field validation failure (`details.fields` when per-field) |
| 422 | `business_rule_violation` | Domain refusal (negative stock, credit limit, closed period) |
| 429 | `rate_limited` | Too many requests (600/min general, 20/min for login by default) |
| 500 | `internal_error` | Unexpected failure — logged with the request id |

Every response carries `X-Request-Id` and `X-Process-Time-Ms`.

## 4. Collections

All list endpoints share one contract:

```
GET /api/v1/<collection>?page=1&page_size=25&q=search&sort_by=code&sort_dir=asc
```

```json
{ "items": [ ... ], "total": 132, "page": 1, "page_size": 25, "pages": 6 }
```

* `page_size` is capped at 200 (documents additionally accept `limit<=200`).
* Document collections add `status`, `date_from`, `date_to`, `party_id`, `branch_id`,
  `warehouse_id`, `open_only`.
* `GET /lookups/{name}` returns compact `{id,label}` rows for form dropdowns. Available
  names: `currencies`, `countries`, `cities`, `taxes`, `payment-terms`, `units`, `branches`,
  `departments`, `cost-centers`, `customers`, `suppliers`, `products`, `warehouses`.
* CSV/Excel export of any collection is a download ticket with `kind=entity`.

## 5. Documents

Every document type exposes the same surface, for example sales orders:

| Method | Path | Description |
| --- | --- | --- |
| GET | `/sales-orders` | List with filters and pagination |
| POST | `/sales-orders` | Create a draft (lines included) |
| GET | `/sales-orders/{id}` | Header, lines, totals, attachments, audit timeline |
| PATCH | `/sales-orders/{id}` | Update while `draft` or `rejected` |
| DELETE | `/sales-orders/{id}` | Delete a draft (soft delete, audited) |
| POST | `/sales-orders/{id}/submit` | Enter the approval chain |
| POST | `/sales-orders/{id}/approve` | Approve the current step |
| POST | `/sales-orders/{id}/reject` | Reject (body requires `reason`) |
| POST | `/sales-orders/{id}/post` | Post to the ledger/inventory |
| POST | `/sales-orders/{id}/unpost` | Reverse a posting (body requires `reason`) |
| POST | `/sales-orders/{id}/cancel` | Cancel a non-posted document |
| POST | `/sales-orders/{id}/print` | Printable HTML (or a download ticket with `file_format=print`) |

Type-specific routes exist where the flow needs them, for example
`POST /sales-orders/{id}/confirm`, `POST /delivery-notes/{id}/post`,
`POST /purchase-orders/{id}/receipt`, `POST /payments/{id}/allocate`,
`POST /production-orders/{id}/complete`, `POST /pos/shifts/{id}/close`.

## 6. Download and print tickets

Long-lived artefacts must not be fetched with the bearer token in a URL, and the web build
cannot attach headers to a browser navigation. The client therefore mints a short-lived
ticket and hands the plain URL to the browser:

```bash
# 1. mint (authorised with the normal bearer token)
curl -s -X POST http://localhost:8080/api/v1/downloads/tickets \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"kind":"report","code":"trial_balance","file_format":"xlsx",
       "parameters":{"date_from":"2026-01-01","date_to":"2026-12-31"}}'

# 2. the browser (or a plain GET) redeems it
curl -s -o trial_balance.xlsx 'http://localhost:8080/api/v1/downloads?token=eyJ...'
```

* `kind` is `report`, `entity` or `document`.
* The minting call checks the caller's permission for that artefact
  (`core.report.export`, `core.import_job.export`, or `<module>.<entity>.print`).
* Tickets are signed JWTs valid for **10 minutes**; redemption re-binds the issuing identity
  and re-resolves the database permissions before rendering, so a revoked user cannot
  redeem an old ticket.
* `file_format` accepts `csv`, `xlsx`, `pdf`, `html` and `print` depending on the artefact.

## 7. Realtime

`WS /api/v1/ws/notifications?token=<access_token>`

* Closes with `4401` when the token is missing/invalid and `4403` when the user lost the
  notification permission.
* Pushes `{"type":"notification", ...}` payloads, `{"type":"unread","unread":n}` counters and
  periodic heartbeats; the client replies to keep the socket alive.

## 8. Conventions worth knowing

* **Money is a string.** Amounts are `Decimal` server-side and serialised as strings
  (`"1234.5000"`); clients format, never float-math.
* **Dates are ISO-8601**, dates without time for document dates, full timestamps with `Z`
  for audit fields.
* **Idempotency by business key.** Creating a document twice with the same number is a
  `conflict`; posting twice is a `conflict`.
* **Reason fields.** `reject` and `unpost` reject the request unless a `reason` is supplied.
* **Rate limiting** is a sliding window per client IP (`RATE_LIMIT_*`), with a stricter
  budget for `/auth/login`.
* **CORS** is configured by `CORS_ORIGINS`; wildcard origins are never combined with
  credentials in production.
