# Technical Requirements Document

## Business Management System

| Document status | Draft for review |
|---|---|
| Version | 1.0 |
| Date | 2026-11-24 |
| Related documents | [PRD](./prd.md), [User flows & UI/UX](./user-flows-ui-ux.md), [System architecture](./system-architecture.md), [ERD](./database-design-erd.md), [API specification](./api-specification.md), [Development task breakdown](./plan.md) |

## 1. Purpose and technical direction

Define a maintainable, secure first-release architecture for the product in [prd.md](./prd.md). Use a modular monolith rather than microservices so a small team can deliver and operate the system simply.

### Required stack

- **Frontend:** React + TypeScript; responsive single-page web application, installable as a PWA.
- **Backend:** Python + Django + Django REST Framework (DRF), version pinned to a supported release at project start.
- **Database:** PostgreSQL, supported release pinned at project start.

### Recommended supporting services

- Object storage for product photos, expense receipts, and generated exports.
- Managed TLS, application hosting, and managed PostgreSQL where available.
- A background worker and queue for large exports when needed. MVP payment recording is manual and does not require provider callbacks or outbound-message delivery.
- Provider adapters for mobile-money/card/bank collection and WhatsApp/SMS/email are deferred to a later release; select vendors only after verifying Liberia onboarding and LRD/USD support.
- Centralized structured application logs, error reporting, uptime checks, and automated database backups.

## 2. System context and deployment shape

```text
Mobile / Desktop browser
        |
        | HTTPS
        v
React + TypeScript web client
        |
        | HTTPS JSON API
        v
Django + DRF modular monolith
    |             |              |
    v             v              v
PostgreSQL   Object storage   Worker + queue
                               (large exports, if needed)
```

- Serve the frontend and API on the same origin when practical; otherwise configure a strict CORS allowlist.
- Store source files, application configuration, and infrastructure configuration in version control. Do not store credentials in the repository.
- Separate development, staging, and production environments. Use synthetic or approved masked data outside production.
- Provision infrastructure repeatably using provider-supported configuration or documented deployment automation.
- Hosting provider, region, domain registrar, and availability tier remain procurement decisions.

## 3. Backend module boundaries

Use Django apps/modules with explicit ownership and shared organization/branch scope:

1. **Identity and access:** accounts, roles, permissions, organization/branch membership.
2. **Organization:** business sections, branches, base currency, time zone, exchange-rate policy, tax/invoice settings.
3. **Catalog and inventory:** products, variants, stock balances, immutable stock movements, cost valuation.
4. **Sales and receivables:** invoices, invoice lines, manually recorded payments, allocations, refunds/reversals, customer balances.
5. **Purchasing and payables:** purchase orders/receipts, supplier bills/payments, landed costs, currency snapshots.
6. **Expenses:** categorized expense records and attachments.
7. **Department orders:** photography, printing, and clothing/custom garment order details and status history.
8. **Currency and FX:** LRD/USD values, approved exchange-rate snapshots, base-currency conversion.
9. **Reporting and notifications:** authorized base-currency aggregates, exports, in-app alerts.
10. **Future integrations (post-MVP):** provider accounts, payment adapters/webhooks, consent-aware message outbox and delivery states.
11. **Audit:** append-only business/security audit events.

Keep workflows in service/domain functions rather than relying on model signals for financial side effects. The API, admin tools, and future integrations must call the same validated business operations.

## 4. Data model and integrity requirements

### Core records and relationships

- `Organization` has many `BusinessSection`, `Branch`, and `UserMembership` records.
- `User` is linked to an organization through membership and receives role/permission scope. Every business record is organization-scoped and, where applicable, branch-scoped.
- `Customer` and `Supplier` can be shared across sections within an organization unless discovery selects isolated records.
- `Product` has optional `ProductVariant` records and an explicit `tracks_stock` flag; services do not affect stock by default.
- `StockMovement` is an immutable quantity delta linked to a source event (opening balance, sale, receipt, return, damage, loss, or adjustment). A cached stock balance may be maintained but must reconcile to the movement ledger.
- `Sale` has `SaleLine` records and one or more `Payment` records. A payment must identify its direction and allocation/source.
- `Purchase` has `PurchaseLine` records, receipt quantities, supplier payment records, and allocated landed costs.
- `Expense` references an expense category and optional uploaded attachment.
- `CustomOrder` stores common order/payment/status data; department-specific details are represented by typed photography, printing, and clothing detail records or equivalent validated fields.
- `OrderStatusHistory` records each transition, actor, time, and optional note.
- `AuditEvent` records actor, organization, action, entity type/ID, timestamp, and safe change metadata.

### Database rules

- Use PostgreSQL `NUMERIC`/Django `DecimalField` for amounts, never binary floating point. Define currency precision and rounding during discovery.
- Support LRD and USD transaction values concurrently, selected per transaction rather than by a global mode. The provisional owner-selected workflow is an authorized owner/admin entering a daily rate; the accountant must approve its source and effective-time rule before launch. Each posted financial record MUST preserve its transaction currency, approved FX rate, rate timestamp/source, and normalized USD amount; never recalculate a historical transaction using today's rate.
- Use USD as this organization's reporting currency. Mixed-currency reports MUST show original-currency subtotals separately and convert consolidated totals with stored/approved rates; detailed reports MUST expose original currency and FX basis.
- Lock the organization reporting base currency after the first posted transaction unless the owner approves a controlled data migration; use explicit snapshots for cross-currency payment allocations.
- Use foreign keys and database constraints for required relationships, positive quantities where appropriate, unique organization-scoped SKU/reference numbers, and valid balances.
- Use `transaction.atomic()` and row-level locking or equivalent safe concurrency control for sale posting, payment allocation, stock receiving, and inventory adjustments.
- The posted stock movement ledger is authoritative. Corrections are compensating movements; do not delete or silently rewrite posted financial or stock events.
- Store timestamps in UTC; present dates in the configured organization/branch time zone.
- Index organization/branch plus frequently filtered fields: transaction date, status, customer/supplier, SKU, invoice/order reference, and payment state.
- Keep uploaded files in private object storage. Validate file type/size, use generated object names, and serve via authorized or short-lived signed URLs.
- Preserve historical price/cost values on transaction lines when catalog prices change.
- Define retention and privacy handling before launch; do not log passwords, tokens, full payment credentials, or unnecessary personal data.

## 5. API requirements

### Conventions

- Versioned JSON REST API under `/api/v1/`.
- Authentication and permissions enforced on every request server-side; never trust frontend-only role checks.
- Consistent validation error structure with field-level errors and a human-readable summary.
- Paginate collections; support explicit sorting and allowlisted filters. Add request size and page-size limits.
- Use idempotency keys for retry-prone financial posting operations where feasible.
- If live payment integrations are added in a later release, payment initiation MUST create a server-side provider intent, callback signatures MUST be verified, and duplicate/out-of-order callbacks MUST be idempotent; redirects alone MUST NOT settle a payment.
- Later-release provider credentials MUST be stored in a secrets manager or secret references; provider event payloads must be minimized and redacted in logs.
- Use ISO-8601 timestamps and decimal amounts serialized as strings or exact JSON numeric values under an explicitly documented contract.
- Return stable identifiers and reference numbers; avoid exposing sequential database IDs as authorization controls.

### Initial resource groups

| Resource group | Representative operations |
|---|---|
| Identity / organization | current user, memberships, roles, business sections, branches |
| Catalog / inventory | products, variants, stock levels, stock movements, adjustments |
| Sales / payments | invoices, invoice lines, post/void, customer payments, receipts |
| Customers / suppliers | profiles, transaction history, balances |
| Purchasing | purchases, receipt confirmation, supplier payments |
| Expenses | expense categories, expenses, attachment upload |
| Orders | photography, printing, clothing orders, status transitions |
| Dashboard / reports | filtered summaries, report data, PDF/spreadsheet export |
| Notifications / audit | in-app alerts, audit search (permission-restricted) |

Do not expose a generic unrestricted CRUD endpoint for posting money or stock; use explicit validated operations for preview, post, receive, manually record/allocate payment, reverse, and adjust. Add provider-intent and callback operations only in a later integration release.

## 6. Financial and inventory workflow rules

1. **Sale posting:** validate organization scope, user permission, product status, prices/discount policy, available stock policy, currency, FX snapshot, and payment total; create invoice, payment allocation, and stock movement atomically.
2. **Purchase receiving:** record ordered and received quantities separately. Increase stock only for confirmed received quantities; repeated receive requests must be idempotent.
3. **Manual payment:** payment amount must be positive; method/date/currency/FX and staff actor are recorded, and allocation cannot exceed the allowed remaining balance except a configured customer credit/refund flow. MVP records payments already received outside the system and does not initiate or verify provider transactions.
4. **Reversal:** require permission and reason; create linked reversing entries and restore affected stock/payment balances as applicable.
5. **Cost of goods sold:** preserve cost basis on sold lines. Moving weighted average is the owner-selected MVP starting point, pending accountant approval and confirmation of landed-cost allocation.
6. **Profit reporting:** separate sales from cash collected, inventory purchases from operating expenses, and uncompleted custom-order deposits from recognized sales according to the approved policy.
7. **Concurrent stock operations:** serialize or lock the affected stock balance so concurrent checkouts cannot oversell unintentionally.
8. **Cross-currency allocation:** convert using an explicit approved daily rate snapshot and record both paid currency and allocated base/invoice-currency amounts; never infer or silently update exchange rates.
9. **External communication:** automated external messaging is not part of MVP. Staff may print, download, or manually share receipts; future messaging must honor consent and retain delivery outcomes.

These rules address PRD requirements REQ-006–REQ-020, REQ-030, REQ-037, and REQ-038 and must have automated tests.

## 7. Authentication, authorization, and security

- Use Django's secure password hashing and a supported authentication/session approach. Prefer secure, HttpOnly, SameSite cookies with CSRF protection for a same-origin browser application; do not store long-lived access tokens in local storage.
- Require HTTPS in all deployed environments. Set secure cookie, HSTS, content security, and other appropriate security headers.
- Enforce tenant and branch scoping in querysets and service operations to prevent cross-organization access (IDOR/data leakage).
- Apply least privilege, default-deny permissions, account deactivation, login throttling, password reset protections, and administrator MFA where the chosen identity setup supports it.
- Validate inputs server-side; use Django ORM parameterization, output encoding, upload validation, CSRF defenses, and rate limits on authentication and sensitive endpoints.
- Record financial, inventory, access-control, and authentication changes in an append-only audit log; restrict audit access and avoid recording secrets.
- Store secrets in a managed secret store/environment configuration; rotate keys and credentials. Do not commit credentials or production data.
- Provider webhook signature/replay protection and consent-aware external messaging are mandatory only if those integrations are added in a later release. Do not expose unauthenticated provider callbacks in the manual-payment MVP.
- Scan dependencies and container images on release; patch supported dependencies and document incident/contact procedures.
- Define privacy notices, consent, data export/erasure, and retention in line with applicable local law before production use.

## 8. Frontend and accessibility

- Use TypeScript, reusable form/table components, explicit loading/empty/error states, and a design system optimized for touch screens.
- Support narrow screens from approximately 360 CSS pixels upward without horizontal scrolling for core tasks.
- Make cashier and order-entry forms low-friction: clear labels, sensible defaults, inline validation, keyboard support, and confirmation for irreversible operations.
- Provide accessible names, focus indicators, sufficient contrast, semantic headings, and screen-reader status announcements. Target WCAG 2.2 AA for core workflows.
- Show current business section, branch, currency, date range, and payment status prominently where mistakes are likely.
- PWA installation may be supported; financial posting requires an online connection for MVP.

## 9. Reporting, exports, and notifications

- Compute reports on the server from authorized, consistent queries; report output must use the same business rules as dashboard totals.
- Use pagination/limits for interactive data. Run large exports asynchronously only when measured export time warrants it.
- PDF receipts and report exports must identify the organization, relevant period, filters, currency, and generation time.
- Spreadsheet export must neutralize formula-like user-entered values to prevent spreadsheet formula injection.
- Store temporary exports privately and expire them. Avoid embedding sensitive data in public links.
- In-app notifications remain available. Automated outbound email/SMS/WhatsApp is deferred; MVP receipts are printed, downloaded, or manually shared. Any later outbound integration requires consent handling, delivery visibility, and separate vendor cost approval.

## 10. Backup, recovery, and operations

- Managed PostgreSQL with automated daily encrypted backups and point-in-time recovery if supported by the selected plan.
- Initial retention target: 30 days, subject to provider cost and applicable retention requirements.
- Back up object-storage attachments and application configuration separately; protect backups with least-privilege access.
- Target PRD recovery objectives: RPO ≤ 24 hours and RTO ≤ 8 business hours for initial launch.
- Test restoration before go-live and at least quarterly; document who can initiate restoration and how data integrity is checked.
- Monitor uptime, error rates, disk/database capacity, failed jobs, backup completion, and abnormal authentication attempts.
- Keep production logs access-controlled and define a retention policy; do not place secrets or full customer records in logs.

## 11. Performance, reliability, and scale

- Interactive search/list APIs: target p95 ≤ 2 seconds under the agreed MVP load.
- Dashboard summary APIs: target p95 ≤ 3 seconds under the agreed MVP load.
- Initial sizing: 25 concurrent active users and 100,000 transaction/order records per organization; benchmark using realistic representative data before acceptance.
- Use database indexes and query inspection to prevent N+1 queries; cache only derived, non-authoritative summaries when needed.
- Use health/readiness checks, graceful error handling, database connection limits, and recoverable background jobs.
- Do not claim offline writes, provider availability, high availability, or a specific uptime SLA until validated against the selected infrastructure/provider plans.

## 12. Testing and release gates

- **Unit tests:** price/discount/rounding, payment allocation, stock movements, cost basis, permissions, reporting calculations.
- **Integration tests:** transaction rollback, concurrent stock posting, purchase receipt idempotency, audit creation, organization/branch isolation, attachment access, historical FX snapshots, and base-currency reconciliation.
- **API tests:** validation, pagination, filtering, unauthorized/forbidden responses, export restrictions.
- **Frontend tests:** sale and order-entry flows, error/empty states, responsive critical screens, permission-dependent navigation.
- **End-to-end acceptance:** sale and receipt; partial/manual payment and balance update; purchase receipt; stock adjustment; each department order; report export; role restrictions; backup restore.
- **Security checks:** dependency scanning, common web vulnerability checks, authorization boundary tests, upload validation, and secret handling. Provider signature/replay checks apply when provider integrations are introduced later.
- **Release gates:** migrations tested on staging; automated tests pass; backup verified; role matrix reviewed; owner approves accounting calculations, FX policy, and receipt format; rollback procedure documented. Provider sandbox settlement/delivery tests are not MVP gates.

## 13. Delivery pipeline and environments

- Use a reproducible build and automated tests on each change.
- Deploy to staging before production; production releases require approval and a successful database backup.
- Apply schema migrations as a controlled release step with rollback/forward-fix guidance.
- Keep environment-specific configuration outside source code.
- Track released application version and database migration version for support.
- Provide a handover package with source code, environment setup, deployment instructions, backup/restore runbook, admin guide, and known limitations.

## 14. Decisions to finalize before implementation

1. Supported Django/PostgreSQL versions, hosting provider/region, and cloud account owner. Liberia is preferred; approve a nearby supported region if local hosting is unavailable.
2. Same-origin deployment and identity approach; admin MFA option.
3. Tenant/branch boundaries and whether business sections share customers, stock, and financial data.
4. Confirm the accountant-approved source and effective-time rule for owner/admin-entered daily FX rates, currency precision, tax rules, invoice numbering, and time-zone policy; USD is the selected reporting base currency.
5. Approve the selected moving weighted-average inventory costing method and confirm shipping/landed-cost allocation, returns, refunds, FX gains/losses, provider fees, and order-deposit recognition.
6. Manual opening catalog/stock setup, attachment limits, backup retention, recovery support, and operating budget; no legacy transaction import is planned.
7. For a later integration release, select payment (mobile money/card/bank) and messaging (WhatsApp/SMS/email) providers and verify supported currencies, callbacks, consent, templates, fees, and merchant account ownership. These are not MVP prerequisites.
