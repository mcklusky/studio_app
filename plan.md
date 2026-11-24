# 06 Development Task Breakdown

## Business Management System — Implementation Plan

| Status | Draft 1.0 |
|---|---|
| Date | 2026-11-24 |
| Source requirements | [PRD](./prd.md) |
| Design inputs | [UI/UX](./user-flows-ui-ux.md), [Architecture](./system-architecture.md), [ERD](./database-design-erd.md), [API](./api-specification.md), [TRD](./trd.md) |

## Summary

Deliver the responsive React/TypeScript client and Django REST Framework/PostgreSQL backend as a modular monolith. Establish organization/role boundaries and the shared catalog first, then implement inventory, sales, manual payment records, LRD/USD transactions with USD base reporting, department orders, reporting/search, and production hardening. Live payment and messaging integrations, along with offline transaction writes, are deferred to later releases.

## Technical Context

**Frontend:** React + TypeScript responsive web/PWA  
**Backend:** Python + Django + Django REST Framework  
**Database:** PostgreSQL  
**Storage:** PostgreSQL for structured records; private object storage for attachments and generated files  
**Authentication:** Secure browser session cookies and CSRF protection, with organization/section/branch authorization  
**Currency:** Concurrent per-transaction LRD/USD values, USD reporting base, separate currency subtotals, and immutable FX snapshots  
**Integrations:** None in MVP; provider-based payment and messaging integrations are deferred
**Testing:** Backend unit/API/integration tests; frontend component tests; manual-payment and end-to-end acceptance flows
**Target:** Current supported Android/iOS and desktop browsers  
**Performance:** PRD NFR-02/NFR-04 targets; benchmark agreed test data before launch  
**Constraints:** No repository or constitution was supplied. Final country, currency, tax, inventory accounting, data-sharing, and provider choices must be approved before production.

## Constitution Check

- **Maintainability:** Pass — one modular monolith, explicit domain services, and documented API/data contracts.
- **Security and privacy:** Pass — server-side scope checks, least privilege, private uploads, auditability, and protected backups.
- **Financial/data integrity:** Pass — decimal amounts, transactional posting, immutable movements, idempotency, and reversals.
- **Usability/accessibility:** Pass — responsive forms, explicit errors, keyboard support, and WCAG 2.2 AA target.
- **Unresolved policy:** Conditional — do not sign off financial reports until tax, costing, returns, and deposit treatment are approved.

## Applied Guidelines

- Follow the security, data-integrity, API, and accessibility requirements documented in the project's [TRD](./trd.md).
- No migration-specific guidelines or repository constitution were provided. Revisit framework-supported security and deployment guidance when implementation versions and hosting provider are selected.

## Implementation Steps

### Phase 1 — Setup

#### Step 1.1 — Initialize the application workspace
- **Requirements:** REQ-034, NFR-06
- **Design inputs:** [Architecture](./system-architecture.md), [TRD](./trd.md)
- **Description:** Establish the proposed frontend/backend project layout, local development configuration, supported dependency versions, and safe environment-variable handling.

Tasks:

- [x] T001 [Plan:1.1] Create `frontend/` React + TypeScript application scaffold with production build and development scripts.
- [x] T002 [P] [Plan:1.1] Create `backend/` Django project and DRF application scaffold with environment-specific settings.
- [x] T003 [P] [Plan:1.1] Add local PostgreSQL configuration and `.env.example` without credentials in `backend/` and root configuration.
- [x] T004 [Plan:1.1] Add lint, format, type-check, test, and build commands for `frontend/` and `backend/`. *(Done: backend `ruff check` / `ruff format` (`backend/ruff.toml`, `requirements-dev.txt`); frontend `npm run lint | format:check | typecheck | build`, all in one `npm run check`. Commands in README → Checks.)*

#### Step 1.2 — Establish quality automation
- **Requirements:** REQ-031–REQ-035
- **Design inputs:** [TRD testing/release requirements](./trd.md)
- **Description:** Add continuous validation, migration checks, and safe staging/production configuration boundaries.

Tasks:

- [x] T005 [Plan:1.2] Configure CI to run frontend checks, backend checks, database-backed tests, and production builds. *(Done: `.github/workflows/ci.yml` runs backend lint, format, system, migration and `check --deploy` checks; tests on PostgreSQL 17; the frontend `npm run check`; then builds both production images. Workflows pass actionlint.)*
- [x] T006 [Plan:1.2] Add dependency and secret scanning jobs and document environment-variable requirements in `README.md`. *(Done: `.github/workflows/security.yml` runs pip-audit, npm audit and a gitleaks full-history scan on every push and weekly; Dependabot is in `.github/dependabot.yml`; README lists every environment variable. The first audit found advisories in Pillow 12.3 and DRF 3.16, now upgraded to Pillow 13.0 and DRF 3.18.)*

#### Step 1.3 — Record financial decisions and future integration discovery
- **Requirements:** REQ-037 (MVP); REQ-030 and REQ-038 (Later)
- **Design inputs:** [PRD open decisions](./prd.md), [API specification](./api-specification.md), [Quotation](./quotation.md)
- **Description:** Record provisional financial choices and publicly available provider research. USD remains the reporting base; owner/admin daily-rate entry and moving weighted-average costing await accountant approval. Provider selection is useful for future planning but does not gate the manual-payment MVP.

Tasks:

- [x] T007 [Plan:1.3] Record preliminary Liberia payment/messaging provider findings, public prices, and verification questions in `provider-research.md`; no provider is selected for MVP.
- [x] T008 [Plan:1.3] Record USD base reporting, provisional owner/admin-entered daily FX rates, moving weighted-average costing, and required accountant approvals in `prd.md`, `trd.md`, and `provider-research.md`.

### Phase 2 — Foundational capabilities

#### Step 2.1 — Organization, branch, and identity foundation
- **Requirements:** REQ-001, REQ-002, REQ-031
- **Design inputs:** [ERD organization/access model](./database-design-erd.md), [Architecture](./system-architecture.md)
- **Description:** Implement organization-scoped records, memberships, section/branch context, authentication, and initial role/permission models.

Tasks:

- [x] T009 [Plan:2.1] Create organization, business-section, branch, membership, role, and permission models and migrations in `backend/apps/organizations/` and `backend/apps/identity/`.
- [x] T010 [P] [Plan:2.1] Configure secure session authentication, CSRF, password reset hooks, and login throttling in `backend/config/`.
- [x] T011 [Plan:2.1] Implement organization/section/branch scoping helpers and default-deny permission checks in `backend/apps/identity/`.
- [x] T012 [Plan:2.1] Add organization-isolation and role-scope tests in `backend/apps/identity/tests/`.

#### Step 2.2 — Shared business records
- **Requirements:** REQ-010, REQ-013, REQ-019
- **Design inputs:** [ERD](./database-design-erd.md), [TRD](./trd.md)
- **Description:** Build shared customers, suppliers, product catalog, categories, variants, expenses, and private attachment support used by later stories.

Tasks:

- [x] T013 [Plan:2.2] Create customer, supplier, product, product-variant, and category models with organization-scoped constraints in `backend/apps/catalog/`.
- [x] T014 [P] [Plan:2.2] Create expense-category, expense, and attachment metadata models in `backend/apps/expenses/` and `backend/apps/files/`.
- [x] T015 [Plan:2.2] Add customer/supplier/product/expense serializers, scoped querysets, and CRUD APIs in `backend/apps/catalog/api/` and `backend/apps/expenses/api/`.
- [x] T016 [Plan:2.2] Implement private upload validation, storage adapter, and authorized downloads in `backend/apps/files/`.

#### Step 2.3 — Shared API and audit foundations
- **Requirements:** REQ-026, REQ-032, REQ-035
- **Design inputs:** [API specification](./api-specification.md), [ERD](./database-design-erd.md)
- **Description:** Establish common errors, pagination, request IDs, audit event writing, and safe idempotency support.

Tasks:

- [x] T017 [Plan:2.3] Configure `/api/v1/` routing, pagination, filtering, validation-error envelope, and request correlation in `backend/config/api.py`.
- [x] T018 [Plan:2.3] Create append-only audit event model and domain service in `backend/apps/audit/`.
- [x] T019 [Plan:2.3] Add reusable idempotency-key persistence and conflict handling for financial operations in `backend/apps/common/idempotency.py`.

#### Step 2.4 — Responsive application shell
- **Requirements:** REQ-034, REQ-035
- **Design inputs:** [UI/UX specification](./user-flows-ui-ux.md)
- **Description:** Implement accessible navigation, organization/branch context, shared form controls, and global loading/error/empty states.

Tasks:

- [x] T020 [Plan:2.4] Build responsive app shell, permission-aware navigation, and section/branch selector in `frontend/src/app/`. *(Done: the top-bar section/branch selector (`app/FocusSelector.tsx`) narrows reads through `X-Section-ID` / `X-Branch-ID` (`focus_on_view` in `apps/identity/scope.py`). It can never widen scope, writes ignore it, and the choice is remembered per organization. Alerts stay unfiltered. Hidden on phones ≤540px.)*
- [x] T021 [P] [Plan:2.4] Create accessible form, table, dialog, status badge, date filter, and error components in `frontend/src/components/`. *(Done: `components/DateRangeFilter.tsx` (any date, today, week, month, year, custom) on the Sales and Purchases lists; shared date helpers in `lib/dates.ts`, also used by Reports.)*
- [x] T022 [Plan:2.4] Add authentication, current-user, organization-context, and API error handling in `frontend/src/features/identity/`.

### Phase 3 — US-06: Staff access and accountability (P1)

#### Step 3.1 — Staff and role management
- **Requirements:** REQ-002, REQ-031
- **Design inputs:** [PRD US-06](./prd.md), [UI/UX](./user-flows-ui-ux.md)
- **Description:** Allow admins to manage users, assign roles and scope, and deactivate accounts without losing historical attribution.

Tasks:

- [x] T023 [US6] [Plan:3.1] Implement staff list, invite/create, role assignment, section/branch scope, and deactivation APIs in `backend/apps/identity/`.
- [x] T024 [US6] [Plan:3.1] Build staff and role administration screens in `frontend/src/features/staff/`.
- [x] T025 [US6] [Plan:3.1] Add API and UI tests for role changes, deactivated users, and denied actions in `backend/apps/identity/tests/` and `frontend/src/features/staff/`. (Backend API tests done; the frontend has no automated UI tests yet. Screens were checked by hand.)

#### Step 3.2 — Audit coverage
- **Requirements:** REQ-032
- **Design inputs:** [ERD audit model](./database-design-erd.md)
- **Description:** Ensure sensitive business and access-control operations emit safe audit events.

Tasks:

- [x] T026 [US6] [Plan:3.2] Add audit service calls for account, role, permission, and organization setting changes in `backend/apps/identity/`.
- [x] T027 [US6] [Plan:3.2] Add permission-restricted audit search API and activity-history view in `backend/apps/audit/` and `frontend/src/features/audit/`.

### Phase 4 — US-02: Inventory and purchasing (P1)

#### Step 4.1 — Stock model and movement ledger
- **Requirements:** REQ-013, REQ-017, REQ-018, REQ-020
- **Design inputs:** [ERD inventory model](./database-design-erd.md), [TRD financial/inventory rules](./trd.md)
- **Description:** Implement stock balances, immutable movement ledger, opening balances, and controlled adjustments.

Tasks:

- [x] T028 [US2] [Plan:4.1] Create stock balance, stock movement, and adjustment models with database constraints in `backend/apps/inventory/`.
- [x] T029 [US2] [Plan:4.1] Implement locked stock update, movement reconciliation, adjustment authorization, and weighted-average-cost services in `backend/apps/inventory/services/`.
- [x] T030 [US2] [Plan:4.1] Build product inventory, movement history, and adjustment screens in `frontend/src/features/inventory/`.
- [x] T031 [US2] [Plan:4.1] Add tests for movement reconciliation, adjustment reasons, thresholds, and concurrent stock updates in `backend/apps/inventory/tests/`. *(Done: `test_concurrency.py` runs simultaneous requests on PostgreSQL. The last unit sells once, a balance can't be paid twice, and receipt numbers stay unique. These tests skip on SQLite.)*

#### Step 4.2 — Purchases and goods receiving
- **Requirements:** REQ-011, REQ-015, REQ-016
- **Design inputs:** [ERD purchase/receipt model](./database-design-erd.md), [API specification](./api-specification.md)
- **Description:** Record supplier purchases, partial receipts, costs, and supplier obligations; increase stock only from confirmed receipts.

Tasks:

- [x] T032 [US2] [Plan:4.2] Create purchase, purchase-line, goods-receipt, and receipt-line models in `backend/apps/purchasing/`.
- [x] T033 [US2] [Plan:4.2] Implement idempotent receipt posting, stock movements, cost allocation, supplier balance services, and audited purchase reversals in `backend/apps/purchasing/services/`.
- [x] T034 [US2] [Plan:4.2] Add purchase create/detail/receive APIs and forms in `backend/apps/purchasing/api/` and `frontend/src/features/purchasing/`.
- [x] T035 [US2] [Plan:4.2] Test partial receipt, duplicate request, invalid quantity, and rollback behavior in `backend/apps/purchasing/tests/`.

#### Step 4.3 — Low-stock visibility
- **Requirements:** REQ-018, REQ-027
- **Design inputs:** [UI/UX](./user-flows-ui-ux.md)
- **Description:** Expose low/out-of-stock state and actionable in-app inventory alerts.

Tasks:

- [x] T036 [US2] [Plan:4.3] Implement low-stock/out-of-stock queries and inventory alert generation in `backend/apps/notifications/`. *(Done in Phase 9: `stock_out` / `stock_low` alerts in `apps/notifications/services.py`.)*
- [x] T037 [US2] [Plan:4.3] Build low-stock product views and alert links in `frontend/src/features/inventory/` and `frontend/src/features/notifications/`. *(Done: low/out-of-stock views, and alerts that open Inventory filtered to the item.)*

### Phase 5 — US-01: Sales and receipts (P1)

#### Step 5.1 — Transactional sale posting
- **Requirements:** REQ-006, REQ-007, REQ-012, REQ-014
- **Design inputs:** [API examples](./api-specification.md), [ERD](./database-design-erd.md)
- **Description:** Implement sale calculation, posting, stock decrement, audit, and reversal as validated server-side business operations.

Tasks:

- [x] T038 [US1] [Plan:5.1] Create sale and sale-line models with immutable price/cost snapshots in `backend/apps/sales/`.
- [x] T039 [US1] [Plan:5.1] Implement decimal-safe totals, permission checks, stock locking, atomic posting, and reasoned reversal services in `backend/apps/sales/services/`.
- [x] T040 [US1] [Plan:5.1] Add sale preview/create-and-post/list/detail/reverse APIs with idempotency handling in `backend/apps/sales/api/`.
- [x] T041 [US1] [Plan:5.1] Build cashier checkout, review, payment entry, and sale-detail screens in `frontend/src/features/sales/`.
- [x] T042 [US1] [Plan:5.1] Test concurrent checkout, out-of-stock rejection, rollback, totals, and reversal behavior in `backend/apps/sales/tests/`.

#### Step 5.2 — Receipt generation and sharing
- **Requirements:** REQ-009
- **Design inputs:** [UI/UX sale flow](./user-flows-ui-ux.md), [API specification](./api-specification.md)
- **Description:** Generate authorized receipts with transaction snapshots and provide print/download/share actions.

Tasks:

- [x] T043 [US1] [Plan:5.2] Implement receipt rendering and authorized PDF response in `backend/apps/sales/receipts/`. *(Done: `apps/sales/receipts.py` renders a 76 mm PDF from the same data as the screen. `GET /api/v1/sales/{id}/receipt/` needs `sales.view` and the sale's section/branch scope, is audited, and is never cached. Costs never appear.)*
- [x] T044 [US1] [Plan:5.2] Add print, download, and device-share receipt actions in `frontend/src/features/sales/`. *(Done: Print, Download PDF and Share; Share uses the device share sheet, or copies to the clipboard where there isn't one.)*
- [x] T045 [US1] [Plan:5.2] Test receipt totals, permissions, and private access in `backend/apps/sales/tests/`. *(Done: `apps/sales/tests/test_receipts.py` checks totals, payments and change, the VOID mark on reversed sales, that costs never appear, scope and organization isolation, and the audit record.)*

### Phase 6 — US-03: Balances, payments, and expenses (P1)

#### Step 6.1 — Customer and supplier payments
- **Requirements:** REQ-008, REQ-010, REQ-011, REQ-012
- **Design inputs:** [ERD payment allocations](./database-design-erd.md), [API specification](./api-specification.md)
- **Description:** Record partial/multiple payments, allocate them to invoices/orders/purchases, and preserve reversals.

Tasks:

- [x] T046 [US3] [Plan:6.1] Create customer/supplier payment and allocation models with database constraints in `backend/apps/payments/`.
- [x] T047 [US3] [Plan:6.1] Implement payment allocation, balance calculation, overpayment handling, and reversal services in `backend/apps/payments/services/`.
- [x] T048 [US3] [Plan:6.1] Add customer/supplier payment APIs and history screens in `backend/apps/payments/api/` and `frontend/src/features/payments/`.
- [x] T049 [US3] [Plan:6.1] Test partial payments, multi-allocation, overpayment, reversals, and balance reconciliation in `backend/apps/payments/tests/`.

#### Step 6.2 — Expense tracking
- **Requirements:** REQ-019
- **Design inputs:** [PRD](./prd.md), [ERD](./database-design-erd.md)
- **Description:** Complete expense entry, category management, attachment, and permission behavior.

Tasks:

- [x] T050 [US3] [Plan:6.2] Implement expense validation, audit, list/filter APIs, attachment authorization, and posted-expense reversals in `backend/apps/expenses/`.
- [x] T051 [US3] [Plan:6.2] Build expense entry, category selection, and receipt/photo upload screens in `frontend/src/features/expenses/`.

#### Step 6.3 — Dual-currency transactions and reporting
- **Requirements:** REQ-005, REQ-037
- **Design inputs:** [ERD currency model](./database-design-erd.md), [API currency contract](./api-specification.md)
- **Description:** Support concurrently used LRD/USD transaction currencies, immutable FX snapshots, separate original-currency subtotals, and consolidated reporting in USD.

Tasks:

- [x] T052 [US3] [Plan:6.3] Add currency, exchange-rate, FX snapshot, and base-amount fields/constraints to financial models and migrations in `backend/apps/currencies/`. *(Done: FX snapshot and base amounts on sales, payments, orders, purchases and expenses.)*
- [x] T053 [US3] [Plan:6.3] Implement approved rate lookup, conversion, rate administration APIs, and historical snapshot rules in `backend/apps/currencies/services/`. *(Done: all transactions, expenses included, use `snapshot_for`.)*
- [x] T054 [US3] [Plan:6.3] Add transaction-currency selection and original/base value display to checkout, payment, order, and report screens in `frontend/src/features/`. *(Done: currency choice at checkout, on payments and orders, and the USD/LRD display switch.)*
- [x] T055 [US3] [Plan:6.3] Test concurrent LRD/USD transactions, rate rounding, historical snapshots, separate subtotals, and consolidated USD reports in `backend/apps/currencies/tests/`. *(Done: `apps/currencies/tests/test_currencies.py` covers rounding, date lookup, append-only rates, API permissions, and same-day LRD/USD sales that keep their own snapshot in the report subtotals.)*

#### Step 6.4 — Deferred: live payment collection (post-MVP)
- **Requirements:** REQ-038 (Later); MVP manual payment recording is covered by Step 6.1
- **Design inputs:** [Payment API contract](./api-specification.md), [Payment sequence](./system-architecture.md)
- **Description:** Future release only. This work is excluded from MVP scope, cost, and acceptance. Manual payments received outside the system are recorded in Step 6.1.

Tasks:

- [ ] T056 [Later] [US3] [Plan:6.4] Create payment-intent state model and provider adapter interface with secret references in `backend/apps/payments/providers/`.
- [ ] T057 [Later] [US3] [Plan:6.4] Implement signed callback verification, replay protection, idempotent event processing, settlement reconciliation, and provider audit in `backend/apps/payments/webhooks/`.
- [ ] T058 [Later] [US3] [Plan:6.4] Build provider checkout initiation and pending/success/failure states in `frontend/src/features/payments/`.
- [ ] T059 [Later] [US3] [Plan:6.4] Validate approved provider sandbox flows, duplicate/out-of-order callbacks, refunds/failures, and settlement reconciliation in `backend/apps/payments/tests/`.

### Phase 7 — US-04: Department orders (P1)

#### Step 7.1 — Shared and department-specific order records
- **Requirements:** REQ-021, REQ-022, REQ-023, REQ-025
- **Design inputs:** [ERD](./database-design-erd.md), [UI/UX flows](./user-flows-ui-ux.md)
- **Description:** Implement common order lifecycle and typed photography, printing, and clothing specifications without unintended stock reduction.

Tasks:

- [x] T060 [US4] [Plan:7.1] Create custom order and photography/printing/clothing detail models in `backend/apps/orders/`.
- [x] T061 [US4] [Plan:7.1] Implement department-specific validation, due-date queries, payment balance integration, and stock-link rules in `backend/apps/orders/services/`.
- [x] T062 [US4] [Plan:7.1] Add create/list/detail APIs for each department order type in `backend/apps/orders/api/`.
- [x] T063 [US4] [Plan:7.1] Build photography booking, printing job, and clothing custom-order forms in `frontend/src/features/orders/`.

#### Step 7.2 — Order status and delivery workflow
- **Requirements:** REQ-024, REQ-027
- **Design inputs:** [UI/UX order flow](./user-flows-ui-ux.md)
- **Description:** Record permission-checked state transitions and expose due/pending/overdue orders.

Tasks:

- [x] T064 [US4] [Plan:7.2] Implement allowed order transitions, actor history, and due-date alerts in `backend/apps/orders/services/`. (Due-soon/overdue counts and filters are done; pushed in-app alerts are part of T077–T079.)
- [x] T065 [US4] [Plan:7.2] Add status timeline, delivery actions, and due/pending filters in `frontend/src/features/orders/`.
- [x] T066 [US4] [Plan:7.2] Test invalid transitions, unauthorized status changes, and order audit history in `backend/apps/orders/tests/`.

### Phase 8 — US-05: Dashboard and financial reports (P1)

#### Step 8.1 — Dashboard and report calculations
- **Requirements:** REQ-003, REQ-004, REQ-005, REQ-020, REQ-028
- **Design inputs:** [PRD business rules](./prd.md), [Architecture](./system-architecture.md)
- **Description:** Implement authorized, reconciled, section/branch/date-filtered summaries with explicit sales, cash, purchases, expenses, and profit definitions.

Tasks:

- [x] T067 [US5] [Plan:8.1] Implement financial aggregation/query services and dashboard summary API in `backend/apps/reports/`.
- [x] T068 [US5] [Plan:8.1] Implement sales, expenses, purchases, profit, best-seller, best-customer, stock-value, and debt report endpoints in `backend/apps/reports/`.
- [x] T069 [US5] [Plan:8.1] Build dashboard KPI cards, filters, recent activity, and drill-through links in `frontend/src/features/dashboard/`.
- [x] T070 [US5] [Plan:8.1] Add reconciliation tests for date/section/branch filters, balances, stock valuation, and combined totals in `backend/apps/reports/tests/`.

#### Step 8.2 — Report export
- **Requirements:** REQ-029
- **Design inputs:** [API specification](./api-specification.md), [TRD](./trd.md)
- **Description:** Generate private PDF and spreadsheet-compatible outputs matching report filters and safe against formula injection.

Tasks:

- [x] T071 [US5] [Plan:8.2] Implement bounded PDF and spreadsheet export services with safe cell encoding in `backend/apps/reports/exports/`.
- [x] T072 [US5] [Plan:8.2] Add report export controls, generation state, and download handling in `frontend/src/features/reports/`.
- [x] T073 [US5] [Plan:8.2] Test export scope, filters, formula-like values, private access, and output contents in `backend/apps/reports/tests/`.

### Phase 9 — US-07: Search and notifications (P2)

#### Step 9.1 — Global search and filters
- **Requirements:** REQ-026
- **Design inputs:** [UI/UX navigation](./user-flows-ui-ux.md), [API specification](./api-specification.md)
- **Description:** Implement permission-scoped search for customers, products, suppliers, invoice/order numbers, dates, staff, and payment status.

Tasks:

- [x] T074 [US7] [Plan:9.1] Implement indexed search/filter endpoints with allowlisted fields in `backend/apps/search/`.
- [x] T075 [US7] [Plan:9.1] Build global search, result grouping, and list filters in `frontend/src/features/search/`.
- [x] T076 [US7] [Plan:9.1] Test organization/section/branch boundaries and search response performance in `backend/apps/search/tests/`.

#### Step 9.2 — In-app alerts
- **Requirements:** REQ-027
- **Design inputs:** [PRD](./prd.md), [Architecture](./system-architecture.md)
- **Description:** Deliver in-app low-stock, outstanding balance, and due/pending order notifications.

Tasks:

- [x] T077 [US7] [Plan:9.2] Implement in-app notification generation, recipient scope, and read state in `backend/apps/notifications/`.
- [x] T078 [US7] [Plan:9.2] Build notification list, unread indicator, and authorized record links in `frontend/src/features/notifications/`.
- [x] T079 [US7] [Plan:9.2] Test alert generation, permission-scoped record links, unread state, and due-date boundaries in `backend/apps/notifications/tests/`.

#### Step 9.3 — Deferred: consent-aware customer messaging (post-MVP)
- **Requirements:** REQ-030 (Later)
- **Design inputs:** [Messaging API contract](./api-specification.md), [UI/UX communication flow](./user-flows-ui-ux.md)
- **Description:** Future release only. Automated external messaging is excluded from MVP scope, cost, and acceptance; staff may print, download, or manually share receipts.

Tasks:

- [ ] T080 [Later] [US7] [Plan:9.3] Implement per-channel consent/preferences, transactional outbox, provider credentials by secret reference, and retryable delivery worker in `backend/apps/messaging/`.
- [ ] T081 [Later] [US7] [Plan:9.3] Add approved channel adapters/templates, customer preference controls, and delivery status history in `backend/apps/messaging/providers/` and `frontend/src/features/customers/`.
- [ ] T082 [Later] [US7] [Plan:9.3] Test consent/suppression, duplicate dispatch, provider outage/retry, template validation, and delivery callbacks in `backend/apps/messaging/tests/`.

### Phase 10 — Cross-cutting production readiness

#### Step 10.1 — Security, recovery, accessibility, and release
- **Requirements:** REQ-031–REQ-035; NFR-01–NFR-10
- **Design inputs:** [TRD](./trd.md), [Architecture](./system-architecture.md), [UI/UX](./user-flows-ui-ux.md)
- **Description:** Verify operational readiness, accessibility, backups, privacy controls, and handover before production.

Tasks:

- [x] T083 [Cross-cutting] [Plan:10.1] Configure production TLS, security headers, secret management, monitoring, and backup retention in `deploy/`. Include the private uploads volume (`PRIVATE_MEDIA_ROOT`) in backups alongside the database. *(Done: `deploy/` has Caddy HTTPS + headers, gunicorn, nightly checksummed backups with retention, `/api/v1/health/ready/`, request-ID logs, admin error emails. Verified on a local production-stack trial.)*
- [x] T084 [Cross-cutting] [Plan:10.1] Add backup restore procedure, restore verification, and operator runbook in `docs/operations/`. *(Done: `docs/operations/runbook.md`, `deploy/backup/restore.sh`, `manage.py verify_integrity`. Restore drill passed on the trial stack.)*
- [ ] T085 [Cross-cutting] [Plan:10.1] Execute responsive/accessibility, role-boundary, upload-security, and performance acceptance checks in `docs/acceptance/`. *(Partly done: `docs/acceptance/acceptance-checklist.md`. Automated and trial checks pass; real-phone, screen-reader and volume tests remain before go-live.)*
- [x] T086 [Cross-cutting] [Plan:10.1] Prepare manual opening catalog/stock setup, reconciliation report, admin guide, and source handover notes in `backend/management/commands/` and `docs/`. *(Done: `manage.py import_catalog` with `docs/onboarding/catalog-template.csv`, `docs/onboarding/admin-guide.md`.)*
- [ ] T087 [Cross-cutting] [Plan:10.1] Complete owner acceptance for tax, currency, inventory costing, deposit treatment, role matrix, receipt, and report calculations in `docs/acceptance/`. *(Prepared: `docs/acceptance/owner-signoff.md`, awaiting owner/accountant decisions.)*

#### Step 10.2 — Deferred offline capability
- **Requirements:** REQ-036
- **Design inputs:** [PRD non-goals](./prd.md), [TRD](./trd.md)
- **Description:** Do not implement offline transaction writes in MVP; require a separate conflict-resolution/reconciliation design and approved plan before development.

Tasks:

- [x] T088 [Cross-cutting] [Plan:10.2] Record offline transaction entry as a deferred roadmap item requiring conflict resolution, reconciliation, and security design in `docs/roadmap.md`. *(Done: `docs/roadmap.md`.)*

### Phase 11 — Public customer website (required)

#### Step 11.1 — Public storefront, booking requests, and order tracking
- **Requirements:** REQ-039 (Later); online payment additionally depends on REQ-038 / Step 6.4
- **Design inputs:** [PRD later scope](./prd.md), Phase 7 department orders, Phase 10 security baseline
- **Description:** Required (confirmed by the owner, 2026-11-24). A separate, unauthenticated public site under its own route/domain and read-only API namespace (`/api/public/v1/`). It exposes only records staff explicitly publish, never costs, balances, staff, or other customers' data. Booking requests land as *unconfirmed* orders that staff accept or decline; they never post sales or move stock on their own.

Tasks:

- [x] T089 [Plan:11.1] Add public-visibility flags and public descriptions/images for products and service packages, with a staff "Publish to website" control, in `backend/apps/catalog/` and `frontend/src/features/catalog/`. *(Done: `Product.show_online` + `public_description`, "Show this on the website" in the product form, "On website" badge in the list.)*
- [x] T090 [Plan:11.1] Build a separate public API namespace with allow-listed serializers, no session/CSRF coupling to the staff app, rate limiting, and caching in `backend/apps/public_site/`. *(Done: `/api/public/v1/` in `apps/public_site/api.py`: no authentication classes, allow-listed fields, per-visitor rate limits `public_read` 120/min, `public_request` 5/h, `public_track` 20/h; public product images only for published products.)*
- [x] T091 [Plan:11.1] Build booking/quote request forms (photography, printing, custom clothing) that create unconfirmed department orders plus a staff review queue, with spam protection (rate limit + challenge) in `backend/apps/public_site/` and `frontend/src/features/orders/`. *(Done: booking/quote form → `WebsiteRequest` (REQ-0001…) with honeypot + signed form-time token; staff Website page queue with Create order (pre-filled order form, customer matched by phone or added), Call/WhatsApp and Decline; new requests raise an alert. A request never creates an order by itself.)*
- [x] T092 [Plan:11.1] Add order-status lookup by order/receipt number plus phone-number second factor, showing status and amount due only, in `backend/apps/public_site/`. *(Done: order or receipt number + phone (last 7 digits must match); same "not found" message for any mismatch; shows status steps, due date, total, paid and balance only.)*
- [x] T093 [Plan:11.1] Build the branded, mobile-first public site (home, services/prices, booking, track order, contact/location) as a separate Vite entry in `frontend/src/public/`. *(Done: `frontend/site/index.html` + `src/public/`, served at `/site/` (Caddy `handle /site*`); home, services, prices, booking, track order, contact, WhatsApp button; brand palette.)*
- [x] T094 [Plan:11.1] Test data exposure (no cost/balance/PII leakage), enumeration resistance on order lookup, rate limits, and request-to-order acceptance in `backend/apps/public_site/tests/`. *(Done: `apps/public_site/tests/test_public_site.py`, 9 tests: exposure, disabled site, honeypot/fast/forged form, request and tracking rate limits, tracking mismatch, staff queue and permissions.)*
- [ ] T095 [Plan:11.1] (Waits for a payment provider, Step 6.4.) After Step 6.4 ships, add optional online deposit/balance payment from the order-tracking page using provider payment intents.

## Project Structure

```text
frontend/
  src/app/
  src/components/
  src/features/{identity,staff,catalog,inventory,sales,purchasing,payments,currencies,expenses,orders,dashboard,reports,search,notifications,customers}/
backend/
  config/
  apps/{organizations,identity,catalog,inventory,sales,purchasing,payments,currencies,expenses,orders,reports,search,notifications,messaging,audit,files,common}/
  tests/
deploy/
docs/
```

`payments` in MVP covers manually recorded payments and allocations. Provider intents/webhooks and the `messaging` integration app are future-release scope only.

## Requirement Mapping

| REQ ID | Description | Plan items | Implementation evidence |
|---|---|---|---|
| REQ-001 | Organization, sections, branches, combined view | 2.1, 8.1 | `backend/apps/organizations/`, `backend/apps/reports/` |
| REQ-002 | Staff accounts, roles, scoped permissions | 2.1, 3.1 | `backend/apps/identity/`, `frontend/src/features/staff/` |
| REQ-003 | Dashboard totals and recent activity | 8.1 | `backend/apps/reports/`, `frontend/src/features/dashboard/` |
| REQ-004 | Dashboard date/section/branch filters | 8.1 | `backend/apps/reports/`, `frontend/src/features/dashboard/` |
| REQ-005 | Currency, period, sales/cash/profit distinctions | 6.3, 8.1 | `backend/apps/currencies/`, `backend/apps/reports/` |
| REQ-006 | Sale entry with customer/items/discount/payment | 5.1 | `backend/apps/sales/`, `frontend/src/features/sales/` |
| REQ-007 | Decimal-safe totals and balances | 5.1, 6.1 | `backend/apps/sales/services/`, `backend/apps/payments/services/` |
| REQ-008 | Partial customer payments | 6.1 | `backend/apps/payments/` |
| REQ-009 | Printable/downloadable/shareable receipt | 5.2 | `backend/apps/sales/receipts/`, `frontend/src/features/sales/` |
| REQ-010 | Customer/supplier profiles and histories | 2.2, 6.1 | `backend/apps/catalog/`, `backend/apps/payments/` |
| REQ-011 | Supplier partial payments and balances | 4.2, 6.1 | `backend/apps/purchasing/`, `backend/apps/payments/` |
| REQ-012 | Authorized reversals; immutable posted history | 5.1, 6.1 | `backend/apps/sales/services/`, `backend/apps/payments/services/` |
| REQ-013 | Product/service catalog and variants | 2.2, 4.1 | `backend/apps/catalog/`, `backend/apps/inventory/` |
| REQ-014 | Atomic stock decrement on sale | 5.1 | `backend/apps/sales/services/`, `backend/apps/inventory/` |
| REQ-015 | Purchase records and costs | 4.2 | `backend/apps/purchasing/` |
| REQ-016 | Stock increases only on confirmed receipt | 4.2 | `backend/apps/purchasing/services/` |
| REQ-017 | Reasoned stock movement adjustments | 4.1 | `backend/apps/inventory/` |
| REQ-018 | Low/out-of-stock thresholds and views | 4.1, 4.3 | `backend/apps/inventory/`, `frontend/src/features/inventory/` |
| REQ-019 | Expense records and attachments | 2.2, 6.2 | `backend/apps/expenses/`, `backend/apps/files/` |
| REQ-020 | Inventory value and valuation basis | 4.1, 8.1 | `backend/apps/inventory/`, `backend/apps/reports/` |
| REQ-021 | Photography bookings and delivery | 7.1, 7.2 | `backend/apps/orders/`, `frontend/src/features/orders/` |
| REQ-022 | Printing orders and production status | 7.1, 7.2 | `backend/apps/orders/` |
| REQ-023 | Clothing/custom garment orders | 7.1 | `backend/apps/orders/` |
| REQ-024 | Permission-checked status history | 7.2 | `backend/apps/orders/services/` |
| REQ-025 | Separate orders; configured material stock only | 7.1 | `backend/apps/orders/services/` |
| REQ-026 | Search and filters | 9.1 | `backend/apps/search/`, `frontend/src/features/search/` |
| REQ-027 | In-app operational and debt alerts | 4.3, 7.2, 9.2 | `backend/apps/notifications/`, `frontend/src/features/notifications/` |
| REQ-028 | Financial and operational reports | 8.1 | `backend/apps/reports/` |
| REQ-029 | PDF and spreadsheet exports | 8.2 | `backend/apps/reports/exports/` |
| REQ-030 | (Later) Consent-aware email/SMS/WhatsApp receipts, reminders, and order updates | 1.3, 9.3 | `backend/apps/messaging/`, `frontend/src/features/customers/` |
| REQ-031 | Individual authentication and server-side authorization | 2.1, 3.1 | `backend/apps/identity/`, `backend/config/` |
| REQ-032 | Audit events | 2.3, 3.2 | `backend/apps/audit/`, `backend/apps/identity/` |
| REQ-033 | Encrypted backup and restore | 10.1 | `deploy/`, `docs/operations/` |
| REQ-034 | Responsive supported browsers/devices | 1.1, 2.4, 10.1 | `frontend/`, `docs/acceptance/` |
| REQ-035 | Validated forms and recoverable errors | 2.3, 2.4, 10.1 | `backend/config/api.py`, `frontend/src/components/` |
| REQ-036 | Optional offline writes (deferred) | 10.2 | `docs/roadmap.md` |
| REQ-037 | Concurrent LRD/USD transactions with separate subtotals and USD consolidation | 1.3, 6.3 | `backend/apps/currencies/`, `frontend/src/features/`, `backend/apps/reports/` |
| REQ-038 | (Later) Provider-based mobile-money/card/bank collection | 1.3, 6.4 | `backend/apps/payments/providers/`, `backend/apps/payments/webhooks/`, `frontend/src/features/payments/` |
| REQ-039 | Public customer website: storefront, booking requests, order tracking | 11.1 | `backend/apps/public_site/`, `frontend/src/public/` |
