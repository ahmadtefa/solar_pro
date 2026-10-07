# Permissions and security

## 1. Model

Roles are collections of permission codes; users receive roles per company (and optionally
per branch/warehouse). The catalogue currently contains **16 modules, 159 entities and 1113
permission codes**, each of the form:

```
<module>.<entity>.<action>          e.g. sales.invoice.post
```

| Action | Applies to | Notes |
| --- | --- | --- |
| `view` | everything | list + detail |
| `create` | master data, documents | create a draft |
| `edit` | master data, documents | only while the document is editable |
| `delete` | master data, draft documents | soft delete, audited |
| `approve`, `reject` | documents | workflow steps |
| `post`, `unpost` | financial/inventory documents | ledger effects; `unpost` requires a reason |
| `submit`, `cancel` | documents | lifecycle transitions |
| `print`, `export`, `import` | reports and collections | artefacts |
| `issue`, `receive`, `transfer`, `close`, `allocate`, … | where the domain needs a verb | declared in the catalogue, not improvised in routes |

Reports additionally accept the fixed triple `("view", "export", "print")`
(`core.report.*`), and saved reports use the entity `saved_report`
(`core.saved_report.view|create|edit|delete`).

### Enforcement points

1. **Router** — every route declares the code it needs; `current.require("<code>")` raises
   `permission_denied` (HTTP 403) when it is missing. Unknown codes are treated as missing,
   so a typo can never silently open a door.
2. **Service** — destructive or lifecycle operations re-check inside the service
   (`ensure_editable`, `can_transition`, posting guards), so a route added later cannot
   bypass the rule.
3. **Tenant filter** — the company scope is applied to every query, so an id from another
   company returns `not_found` rather than leaking existence.
4. **Client** — `AuthState.can(code)` hides menus and buttons the user cannot use. This is
   cosmetic: the server never trusts it.

A regression test parses every router in the project and asserts that every permission code
it mentions exists in the catalogue (`tests/test_platform.py::test_router_permissions_exist`),
which is how the 407 route references stay aligned with the 1113 codes.

## 2. Data scope

Roles also carry a `data_scope`:

| Scope | Sees |
| --- | --- |
| `company` | Everything in the company |
| `branch` | Only rows of the user's branches (documents, warehouses, employees) |
| `warehouse` | Only stock and documents of the user's warehouses |
| `own` | Only documents they created/own (sales representative, technician) |
| `team` | Their team's rows (manager dashboards) |

The scope is applied to list queries and to aggregate dashboards; it never widens
permissions, it only narrows visibility.

## 3. Role templates

Sixteen templates ship with the platform and are provisioned per company. They are starting
points: every one can be edited afterwards from **Roles**.

| Template | Intended for | Highlights |
| --- | --- | --- |
| `company_admin` | System owner | Everything except audit-log tampering; can manage companies, users, settings |
| `general_manager` | Management dashboard | Read across modules, approve high-value documents, no configuration |
| `branch_manager` | Branch operations | Branch-scoped sales, inventory, approvals, expenses |
| `sales_manager` | Sales team | Quotations → invoices, approvals, discounts, credit overrides, targets |
| `sales_rep` | Field sales | Own quotations/orders, customer read, no posting |
| `accountant` | Finance | Journals, posting, trial balance, reports, payments, reconciliation |
| `warehouse_manager` | Warehouse | Receipts, issues, transfers, stocktake, approval of adjustments |
| `warehouse_clerk` | Store keeper | Receipts, issues, transfers, counts (no posting) |
| `purchasing_manager` | Procurement | Requests → POs, supplier quotations, approvals |
| `hr_manager` | People | Employees, contracts, attendance, leave, payroll runs |
| `service_manager` | After-sales | Requests, tickets, work orders, contracts, warranties |
| `project_manager` | Projects | Projects, tasks, timesheets, project purchases, billing |
| `manufacturing_manager` | Production | BOMs, routings, production orders, WIP costing |
| `pos_cashier` | Till operator | POS terminals, own shifts, sales and returns only |
| `auditor` | Internal audit | Read everything, export reports, no writes |
| `viewer` | Read-only observer | Read the modules enabled for the company |

Creating a company provisions the administrator role, the default chart of accounts, taxes,
units, payment terms, a main branch and warehouse, and the numbering sequences — all from
`BootstrapService`, so a new tenant is usable immediately.

## 4. Authentication hardening

| Control | Implementation |
| --- | --- |
| Password storage | Bcrypt, `BCRYPT_ROUNDS` (default 12) |
| Password policy | Minimum length + strength validation, `must_change_password` for admin resets |
| Brute force | `login_attempts` per email/IP, lockout for `LOGIN_LOCKOUT_MINUTES` after `LOGIN_MAX_FAILED_ATTEMPTS` |
| Tokens | HS256 JWT with `sub`, `company`, `session`, `permissions_version`, `type` (`access`/`refresh`/`download`); short-lived access tokens |
| Refresh | Rotating refresh tokens bound to the session; refresh of a revoked session fails |
| Sessions/devices | Every login creates a `user_sessions` row (device, IP, user agent, last seen); users can revoke any device |
| Revocation | `permissions_version` bump and session revocation invalidate tokens on the next request |
| Reset flow | `password_reset_tokens` with expiry, single use, never reveals whether an account exists |
| Transport | Bearer over TLS terminated at Nginx; HSTS and security headers in `infrastructure/nginx.conf` |

## 5. Application security

| Risk | Mitigation |
| --- | --- |
| SQL injection | SQLAlchemy parameter binding everywhere; no string-built SQL; `search_fields` are declared columns |
| Cross-tenant access | Session-level company filter + `require()` on every route + `not_found` for foreign ids |
| Privilege escalation | Permissions resolved server side per request; role changes bump `permissions_version` |
| Mass assignment | Pydantic schemas whitelist fields; unknown keys are rejected, not silently stored |
| File upload abuse | Extension whitelist, size limit (`MAX_UPLOAD_SIZE_MB`), stored outside the web root, served only through an authorised endpoint |
| IDOR on documents | Every read goes through the tenant filter and the collection's `view` permission |
| Posting abuse | Immutability of posted documents + reason-required unpost + full audit trail |
| Brute force / DoS | Rate limiting middleware, stricter login budget, capped page sizes |
| Secrets | Environment variables only; `.env` is git-ignored; `.env.example` carries placeholders; `SECRET_KEY` is validated at startup outside development |
| Audit | `audit_logs` records user, company, timestamp, IP, session, action, entity, old/new values for create/update/delete/approve/reject/post/unpost/login/logout and permission changes |

## 6. Operating the permission model

```bash
# which codes does a role have?
curl -s "$API/roles/$ROLE_ID" -H "Authorization: Bearer $TOKEN"

# replace a role's permissions
curl -s -X PUT "$API/roles/$ROLE_ID/permissions" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["sales.invoice.view","sales.invoice.create"]}'
```

* Adding a permission to a role invalidates the cached permission set of its users
  (`permissions_version`).
* Deleting a role is refused while users still reference it.
* Company administrators can enable/disable whole modules per company
  (`module_activations`); disabled modules disappear from navigation and their routes
  answer `403`.
