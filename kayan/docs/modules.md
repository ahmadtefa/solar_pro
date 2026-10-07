# Modules

Each section lists what the module owns, the documents it produces and the workflow it
implements. Document types expose the standard lifecycle described in
[architecture.md](architecture.md#4-document-lifecycle); only module-specific behaviour is
repeated here.

## Platform administration

Companies, branches, departments, divisions, cost centres, countries, cities, addresses,
currencies and historical exchange rates, taxes, payment terms, unit groups and units with
conversion factors, numbering sequences, document types, fiscal years and periods, system
settings and per-company module activation.

* `POST /admin/companies` provisions a tenant (roles, chart of accounts, taxes, units,
  numbering, main branch and warehouse, administrator user).
* `GET/PUT /admin/companies/{id}/modules` toggles modules per company.
* Fiscal periods can be closed and re-opened with an audit trail; posting into a closed
  period is refused.

## Identity, access and audit

Users, roles, permissions, per-company/branch/warehouse access, sessions and devices,
login attempts, password resets, notification preferences, saved reports, import jobs,
backup jobs and the audit log. See [permissions.md](permissions.md).

## CRM

Lead sources, pipeline stages, leads with follow-ups, opportunities with expected value and
probability, activities (calls, meetings, tasks) with reminders, lost reasons, sales targets
and a unified timeline per customer or lead. Conversion of a won opportunity into a customer
and a quotation is a single call.

## Master data

Product categories and brands, the universal item master (stock, service, consumable, asset,
kit, bundle) with SKU, barcode(s), variants, units, min/max/reorder rules and price lists;
customer groups, supplier groups, customers and suppliers with contacts, credit limits,
payment terms, tax data, notes and attachments; warehouses, zones and locations; supplier
products with price history and supplier evaluation scores.

## Inventory

Immutable stock ledger with receipts, issues, transfers, adjustments, stocktake and returns;
batch/lot, expiry and manufacturing date, serial numbers per unit; inventory valuation
layers (moving average) and stock balances rebuilt from the ledger; reorder rules that feed
purchasing suggestions.

* `POST /stock-transfers/{id}/post` moves stock between locations atomically.
* `POST /stock-counts/{id}/post` writes the differences as adjustment entries.
* `POST /stock-adjustments/{id}/post` requires a reason; every ledger row keeps
  `is_reversed`/`reversal_of_id` so corrections never destroy history.

## Purchasing

Purchase request → approval → RFQ → supplier quotations → comparison → purchase order →
goods receipt → purchase invoice → payment, with partial receipts/invoices, discounts,
taxes, returns (debit notes) and supplier evaluation.

* `POST /purchase-requests/{id}/submit|approve` runs the workflow (amount tiers).
* `POST /purchase-orders/{id}/receipt` creates the goods receipt and stocks the goods.
* `POST /goods-receipts/{id}/post` posts inventory; `POST /purchase-invoices/{id}/post`
  posts AP and updates supplier balances.

## Sales

Quotation → sales order → delivery note → sales invoice → receipt, with partial deliveries
and invoices, returns (credit notes), discounts, taxes, credit-limit checks, commissions and
sales targets.

* `POST /sales-orders/{id}/confirm` performs the credit check
  (`allow_credit_override` demands the extra permission).
* `POST /delivery-notes/{id}/post` issues stock; `POST /sales-invoices/{id}/post` posts AR,
  revenue and tax, and links the delivery/invoice chain.
* `POST /credit-notes/{id}/post` handles returns and price corrections.

## Point of sale

Terminals, cashier shifts, barcode/product lookup, touch sales and returns, line and total
discounts, cash/card/wallet/credit payment, cash-in/cash-out movements during a shift, blind
cash reconciliation on close and receipt printing.

* `POST /pos/shifts/open|close`, `POST /pos/cash-movements`, `POST /pos/sales`,
  `POST /pos/returns`, `GET /pos/lookup?q=`.
* A sale posts inventory and accounting immediately; the shift keeps the cash expected
  versus counted difference for reconciliation.

## Accounting

Chart of accounts (multi-level, control accounts for AR/AP), journal entries and lines with
dimensions (branch, cost centre, project), posting rules that map document roles to
accounts, customer/supplier ledger entries, period closes, and reports: general ledger,
trial balance, income statement, balance sheet, cash flow, AR/AP aging and per-party
statements.

* `POST /journal-entries/{id}/post|unpost`, `POST /journal-entries/{id}/reverse`.
* `GET /reports/run/trial_balance`, `.../income_statement`, `.../balance_sheet`,
  `.../cash_flow`, `.../ar_aging`, `.../ap_aging`, `.../ledger`, `.../customer_statement`,
  `.../supplier_statement`.
* Posting is idempotent per document: a second post is a `conflict`, and unposting writes a
  balanced reversal.

## Cash and banks

Cash accounts, bank accounts (with IBAN/SWIFT and chart links), receipts, payments with
allocation to invoices, treasury transfers, cheques (received/issued, deposit, clearance),
bank reconciliation against statements, currency revaluation and cash-flow snapshots.

* `POST /payments/{id}/allocate` applies a payment to one or more invoices; partial
  allocations leave the remainder open.
* `GET /reports/run/cash_book`, `.../daily_collection`, `.../bank_reconciliation`.

## Taxes

Per-company tax configuration: rate, inclusive/exclusive pricing, compound taxes,
withholding, tax accounts and effective dates. No country-specific logic is hardcoded; the
Egyptian defaults only exist in the optional demo seed.

## Fixed assets

Asset categories with depreciation defaults, the asset register (acquisition, capitalisation,
location, custodian, warranty), depreciation runs (straight line, declining balance, units of
production), transfers between branches/custodians, disposals with gain/loss posting and
maintenance schedules.

* `POST /assets/{id}/capitalize`, `POST /asset-depreciations/run`,
  `POST /asset-transfers/{id}/post`, `POST /asset-disposals/{id}/post`.

## Expenses

Expense categories, employee expenses with receipts and lines, expense claims, advances and
settlement, budgets with lines and variance reporting, allocation to cost centres/projects
and payment through treasury.

* `POST /expenses/{id}/submit|approve|post`, `POST /expense-claims/{id}/approve`.

## Projects

Project types, phases, tasks, milestones, budgets, resource plans, materials and purchases,
employee timesheets with billable rates, billing schedules and profitability analysis.

* `POST /timesheets/{id}/submit|approve`, `POST /projects/{id}/billing`,
  `GET /reports/run/project_profitability`.

## Human resources

Employees with documents and contracts, positions, shifts and assignments, attendance with
overtime, holidays, leave types/requests/balances, and a configurable, country-independent
payroll engine (periods, runs, payslips, components with formulas and taxable flags, loans
and advances).

* `POST /leave-requests/{id}/submit|approve`, `POST /payroll-runs/{id}/calculate|post`,
  `GET /payslips`.
* Payroll components are data, not code: a new deduction or allowance is a row with an
  amount/formula, scope and taxation flag.

## Manufacturing

Bill of materials with versions and lines, routings and operations with work centres and
times, production orders with material consumption, operation progress, outputs, scrap and
by-products, and WIP costing per order.

* `POST /production-orders/{id}/release|consume|complete`, `POST /production-orders/{id}/scrap`,
  `GET /reports/run/wip_valuation`.

## Service and maintenance

Service requests, tickets with messages and SLA, technician scheduling, work orders with
parts and labour, service contracts (AMC) with covered assets and billing schedules,
warranties and complete service history per asset.

* `POST /service-requests/{id}/convert`, `POST /work-orders/{id}/complete`,
  `GET /tickets/queue`.

## Workflow

Reusable approval engine: definitions per document type, amount-tiered steps, approver types
(role, user, manager, dynamic), conditions, timeouts with automatic actions, delegation and
a full action history.

* `GET /workflow/my-approvals`, `POST /workflow/instances/{id}/decide`,
  `POST /workflow/definitions`, `POST /workflow/delegations`.

## Notifications

Notification centre with read/unread state, per-user preferences per category and channel
(in-app, email, SMS, push, WhatsApp), outbox messages for external channels and live push
over WebSocket.

## Attachments

Generic attachment service for any entity: PDF, JPG, PNG, Excel, Word, CSV, text and ZIP up
to the configured size, stored outside the web root, served only to users who can read the
parent record, with thumbnail metadata and an audit trail.

## Reports, dashboards, search, data tools

* **Report engine** — filters, grouping, sorting, totals and export to PDF/Excel/CSV/print;
  catalogue driven (`GET /reports/catalogue`), runnable ad hoc (`POST /reports/run/{code}`)
  or saved per user (`/reports/saved`).
* **Dashboards** — role templates (management, sales, warehouse, accounting, HR, projects,
  service, manufacturing) with KPI cards, trend charts and lists of recent/overdue work.
* **Global search** — one query across customers, suppliers, products, documents and
  employees, grouped by entity type and filtered by the caller's permissions.
* **Import/export** — CSV/Excel upload → column mapping → validation → preview → import,
  with every invalid row reported (row number + reason) and never silently discarded; export
  of any collection or report.
* **Backup** — manual and scheduled backups with checksum verification, retention, download
  and documented restore procedure, restricted to administrators.
