# Just Smile Empire Business Management System

Responsive business management system for clothing, printing, and photography operations. It is a Django REST Framework API with a React + TypeScript client. It covers sales and receipts, inventory and purchasing, customer and supplier balances, expenses, department orders, dashboard and reports with Excel/PDF export, staff and roles, search, alerts, team chat, uploads, and a public customer website. It works in LRD and USD and reports in USD.

## Local development

1. Copy `.env.example` to `.env` and keep the example credentials for local development only. Without `DATABASE_URL`, the backend falls back to SQLite at `backend/db.sqlite3`.
2. Optional: start PostgreSQL with `docker compose up -d db`.
3. In `backend/`, create and activate a Python 3.13 virtual environment, then install `requirements-dev.txt`. It includes `requirements.txt` plus the lint and audit tools.
4. From `backend/`, run `python manage.py migrate`.
5. Create a workspace, using **one** of the following:
   - **Demo data (local only):** `python manage.py seed_demo` creates "Demo Studio" with `owner`, `cashier` and `printer` (Printing section only) users and prints their generated passwords once.
   - **Real setup:** `python manage.py createsuperuser`, then `python manage.py setup_organization --name "Just Smile Empire" --admin-username <your-username>`.
6. Start the API with `python manage.py runserver`.
7. In `frontend/`, run `npm install` and `npm run dev`, then open the printed URL. The Vite dev server proxies `/api` to `http://127.0.0.1:8000` so session and CSRF cookies stay same-origin. Override the target with `VITE_API_PROXY_TARGET`. If port 5173 is busy, run `npm run dev -- --port 5191`.

### Checks

The same checks run in CI on every push and pull request (`.github/workflows/ci.yml`). Run them before pushing:

| What | Command (backend from `backend/`, frontend from `frontend/`) |
|---|---|
| Backend lint / format | `ruff check .` · `ruff format --check .` (fix with `ruff check --fix .` and `ruff format .`) |
| Backend system and migration check | `python manage.py check && python manage.py makemigrations --check --dry-run` |
| Backend tests | `python manage.py test`. On SQLite the three PostgreSQL race tests are skipped. For the full run: `docker compose up -d db`, then `DATABASE_URL=postgresql://studio_app:local-dev-change-me@localhost:5432/studio_app python manage.py test` |
| Frontend: everything | `npm run check` runs lint, format check, type check and production build |
| Frontend individually | `npm run lint` · `npm run format:check` (fix with `npm run format`) · `npm run typecheck` · `npm run build` |
| Dependency audit | `pip-audit -r requirements.txt` · `npm audit --omit=dev` |

**CI** (`.github/workflows/ci.yml`) runs backend lint, format, system check, migration check, `check --deploy` with production settings, and the full test suite on PostgreSQL 17. That includes the row-lock races: last unit sold twice, a balance paid twice, duplicate receipt numbers. It also runs the frontend `npm run check`, then builds both production Docker images.

**Security** (`.github/workflows/security.yml`, on every push and weekly) runs `pip-audit` and `npm audit` for known vulnerabilities and a gitleaks scan of the full git history for committed secrets (`.gitleaks.toml` lists the documented placeholders it ignores). Dependabot (`.github/dependabot.yml`) opens weekly update pull requests for Python, npm, the Docker base images and the CI actions.

### Environment variables

Local development reads `backend/.env` (template: `backend/.env.example`). Production reads `deploy/.env` (template: `deploy/.env.example`), and `docker-compose.prod.yml` passes the values on. Never commit a filled-in `.env`: both are git-ignored, and the secret scan fails if one is committed.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | unsafe local key | Signs sessions and CSRF tokens. **Required** when `DJANGO_DEBUG=false`; the app refuses to start without a real one. Changing it signs everyone out |
| `DJANGO_DEBUG` | `true` | `false` in production. This turns on secure cookies, the HTTPS redirect, HSTS and the startup guards |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host names. **Required** in production: the app refuses to start with localhost only, unless `DJANGO_ALLOW_LOCALHOST_ONLY=true` |
| `TRUSTED_PROXY_COUNT` | unset | Number of reverse proxies in front of Django (`1` behind Caddy, set in `docker-compose.prod.yml`) so rate limits see each visitor's address |
| `PUBLIC_SITE_ORGANIZATION_ID` | blank | Which organization the public website shows; blank uses the only one with its website switched on |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173` | Comma-separated `https://` origins allowed to post forms (the site's own URL) |
| `DATABASE_URL` | SQLite `backend/db.sqlite3` | PostgreSQL URL; always PostgreSQL in production |
| `PUBLIC_APP_URL` | `http://localhost:5173` (debug only) | The app's public URL, used in links |
| `SESSION_COOKIE_AGE` | `43200` (12 hours) | Sign-in lifetime in seconds |
| `SECURE_SSL_REDIRECT` | `true` (production) | Redirect HTTP to HTTPS inside Django. Caddy already does this |
| `SECURE_HSTS_SECONDS` (`HSTS_SECONDS` in `deploy/.env`) | `3600` | Raise to `31536000` after HTTPS has worked for a few days |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | `false` | Owner decisions; only enable if every subdomain uses HTTPS |
| `DJANGO_ADMIN_URL` (`DJANGO_ADMIN_PATH` in `deploy/.env`) | `admin/` | Location of the Django admin site |
| `DJANGO_ADMINS` | — | `Name email, Name email`: who receives server-error emails |
| `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | — | Outgoing mail (SMTP). `EMAIL_HOST_PASSWORD` is a secret |
| `PRIVATE_MEDIA_ROOT` | `backend/private_media/` | Private upload storage. Back it up with the database |
| `MAX_UPLOAD_BYTES` | `8388608` (8 MB) | Largest accepted upload |
| `STATIC_ROOT` | `backend/staticfiles/` | Where `collectstatic` writes (used by the image build) |
| `LOG_LEVEL` | `INFO` | Backend log level |
| `VITE_API_PROXY_TARGET` (frontend dev only) | `http://127.0.0.1:8000` | Where the Vite dev server forwards `/api` |
| `SITE_DOMAIN`, `POSTGRES_PASSWORD`, `BACKUP_DIR`, `BACKUP_HOUR`, `BACKUP_RETENTION_DAYS`, `TZ` (`deploy/.env` only) | see template | Domain for HTTPS certificates, database password (secret), backup location and schedule, and server time zone |

### API conventions

- All endpoints live under `/api/v1/`. Session authentication endpoints are under `/api/v1/auth/`. `GET /api/v1/organization/` returns the caller's organization, role, permission codes and section/branch scope. Send `X-Organization-ID` when a user belongs to more than one organization; the server only accepts organizations the user is a member of.
- Errors always use `{"error": {"code", "message", "field_errors", "request_id"}}`. Every response carries an `X-Request-ID` header that matches the `request_id` and the audit trail.
- Creates and updates through the shared `ScopedViewSet` (`backend/apps/common/viewsets.py`) write an append-only `AuditEvent`. Contact fields are recorded only as `[changed]`. Owners and managers can read the trail at `/api/v1/audit-events/`.
- Retry-safe financial writes wrap their work in `run_idempotent` (`backend/apps/common/idempotency.py`), keyed by the `Idempotency-Key` header.
- Stock changes only through `apps/inventory/services.py` (`apply_movement`, `adjust_stock`), which locks the balance row, refuses to go below zero, appends an immutable `StockMovement`, and re-averages cost (moving weighted average, in the base currency). Cost fields are returned only to roles holding `inventory.costs`.
- Exchange rates (`/api/v1/exchange-rates/`) are entered daily by owner/admin as LRD per 1 USD and are append-only. LRD transactions snapshot the rate in force on their date (`apps/currencies/services.py`); USD uses 1. Base (USD) amounts are rounded half-up to cents.
- Purchases add no stock until goods are received (`apps/purchasing/services.py`). Receipts may be partial, can never exceed what was ordered, require an `Idempotency-Key`, and spread shipping/other costs across lines by value. Reversing a receipt removes its units at their original landed cost, so the average cost returns to its prior value.
- Sales (`apps/sales/services.py`) are priced by the server from the catalog (converted at the day's rate for LRD). `POST /sales/preview/` prices without saving. `POST /sales/` (requires `Idempotency-Key`) commits the sale, its stock movements, an optional first payment and the audit event in one transaction. Price changes need `sales.price_override`. A sale leaving a balance needs a named customer. Payments can never exceed the balance. `POST /sales/{id}/reverse/` (`sales.reverse`) returns stock at its original cost and reverses the sale's payments. `GET /sales/{id}/receipt/` returns the receipt as a 76 mm PDF (`apps/sales/receipts.py`) for anyone who can view the sale. It is audited, never cached, and never shows costs. A reversed sale prints as VOID.
- **Balances and payments** (`apps/payments/services.py`): customers and suppliers owe per currency (LRD and USD are never added together). `POST /customer-payments/` and `POST /supplier-payments/` (both need an `Idempotency-Key`) allocate to the invoices/purchases you name, or oldest first. They never exceed what is owed. Reversals reopen balances. Reversing a sale refunds only that sale's share of a payment: a payment that also covered other invoices is reversed and re-issued for them. Statements: `GET /customers/{id}/statement/`, `GET /suppliers/{id}/statement/`. Lists accept `?has_balance=true`.
- **Expenses** (`apps/expenses/services.py`) are posted when recorded (EXP-0001), converted at the daily rate for their date, and corrected only by reversal with a reason. `GET /expenses/` returns per-currency and USD totals for the current filter.
- **Department orders** (`apps/orders/`, `/api/v1/orders/`): photography bookings, printing jobs and custom clothing (with size/name/number lines). The department comes from the section. Price and FX snapshot are fixed at creation (ORD-0001); an optional deposit is recorded as a customer payment. Status moves forward through each department's steps (`POST /orders/{id}/status/`); moving back is a correction needing `orders.manage` and a note, and every change is kept in the order history. Price changes need `orders.manage` and never go below what is paid. Cancelling needs a reason and no payments still applied. Orders never move stock unless materials are recorded (`POST /orders/{id}/materials/`, returned at their original cost). Open order balances count in customer balances and statements, and customer payments can settle sales and orders oldest first. `GET /orders/?view=active|due_soon|overdue|unpaid|delivered|cancelled|all` returns tab counts.
- **Dashboard and reports** (`apps/reports/services.py`, `/api/v1/reports/`): one set of definitions feeds the Overview and the Reports page. `dashboard/` (`dashboard.view`) and `summary/`, `products/`, `customers/`, `debts/`, `stock/` (`reports.view`) take `from`, `to`, `section`, `branch`, limited to the caller's sections and branches. Every figure is in USD, converted with each transaction's saved rate, with LRD/USD subtotals beside it. Sales and cash collected are separate. Orders count as revenue when delivered (provisional). Purchases are not an expense, because stock cost reaches profit when it is sold. Gross profit = revenue − cost of goods sold. Net profit = gross profit − expenses. Figures are returned only to roles allowed to see them: profit needs `reports.view` and `inventory.costs`. Balances and stock value are as of now. `apps/reports/tests/` reconciles hand-worked books, including that the sections add up to the combined total.
- **Report exports**: `GET /reports/{summary|products|customers|debts|stock}/export/?file=xlsx|pdf` with the same filters as the screen (`apps/reports/exports.py`). Files state the organization, period, section, branch, who generated them and when, and the currency basis. They are generated in the request and capped at 500 rows. Each export is recorded as an audit event and sent with `Cache-Control: private, no-store`. Spreadsheet text that a spreadsheet could run as a formula is stored as plain text. The query parameter is `file`, because DRF reserves `format`.
- **Search and alerts**: `GET /api/v1/search/?q=` (`apps/search/api.py`) searches an allow-list of fields per record type and returns up to 5 results per group, only for record types the caller may see and within their sections and branches. The top-bar box opens the record (sales, orders, purchases) or the list pre-filtered (everything else). Press `/` to focus it. `GET /api/v1/alerts/` (`apps/notifications/services.py`) works out alerts live: out of stock or low, orders overdue or due today/tomorrow, photo shoots in the next 2 days, customers with an item unpaid for over 14 days, received purchases unpaid for over 30 days, and a missing LRD rate for today. Each alert respects the person's permissions and scope. Only read marks are stored (`AlertRead`). An alert's key includes its state (e.g. the due date), so a changed situation shows up as unread again. `POST /api/v1/alerts/read/` takes `{keys}` or `{all: true}`.
- **Uploads** (`apps/files/`): receipt photos and PDFs on expenses (up to 5) and one photo per product. `POST /api/v1/attachments/` (multipart: `purpose`, `owner`, `file`) and `GET /api/v1/attachments/?purpose=&owner=` list them; `GET /api/v1/attachments/<id>/file/` downloads and `DELETE /api/v1/attachments/<id>/` removes. Files are kept in private storage (`PRIVATE_MEDIA_ROOT`, default `backend/private_media/`, git-ignored) under random names and are never served directly. Every download checks the purpose's permission and the record's section/branch scope. File type is detected from the file's contents: JPEG/PNG/WebP, plus PDF for receipts. Photos are re-saved at no more than 1600 px with all metadata removed, including GPS location. The size limit is `MAX_UPLOAD_BYTES` (8 MB). Uploads and removals are audited. Back up `PRIVATE_MEDIA_ROOT` together with the database.
- **USD/LRD display switch** (`frontend/src/features/currencies/DisplayCurrency.tsx`): one app-wide, remembered setting shown on Overview, Reports, Orders, Products, Inventory, Sales and Purchases. Base (USD) figures convert to LRD at today's rate, and the switch states the rate. Listed transactions in another currency convert using their own saved FX snapshot and keep the original amount underneath. Receipts and transaction details never convert: they show the currency the money actually changed hands in. LRD is disabled until a rate exists.
- **Staff and roles** (`apps/identity/staff.py`): `/api/v1/staff/` (`staff.manage`) adds people, changes their role and section/branch scope, and handles `deactivate/`, `reactivate/` and `reset-password/`. A temporary password is returned once. Accounts are never deleted, so history stays attributed. Safeguards: you cannot deactivate or demote yourself, the last active owner/admin cannot be removed, and only an owner/admin can make another owner/admin. `/api/v1/roles/` lists roles and `catalog/`. Custom roles (`roles.manage`) can only grant permissions the creator holds, and built-in roles are read-only. `POST /api/v1/auth/password/` changes your own password and signs out your other sessions. Sign-ins and all staff, role and password changes are audited. `/api/v1/audit-events/?area=staff,auth&actor=<user id>` filters the activity log.
- **Team chat**: `apps/chat` gives staff one team thread per organization plus one-to-one threads. `GET/POST /api/v1/chat/conversations/` lists threads with unread counts or opens a direct thread (`{user}`). `GET/POST .../conversations/<id>/messages/` reads (`?after=` for polling, `?before=` for older) or sends (max 2,000 characters, 30 a minute). `POST .../read/` marks a thread read, and `GET /api/v1/chat/people/` lists active teammates. Only active members of the organization can use it, and a direct thread hides once the other person is deactivated. The client polls (every 3.5 s in an open thread, 20 s for the unread badge).
- **Public website**: customers use `/site/` (a separate Vite page, `frontend/site/index.html` + `src/public/`) to see services and prices, send booking or quote requests, and track an order. It calls only `/api/public/v1/` (`apps/public_site/api.py`): `site/`, `catalog/`, `catalog/<id>/image/`, `requests/` (POST) and `track/` (POST). These views have no authentication classes, return allow-listed fields only (never costs, stock, staff or other customers) and are rate limited per visitor (`public_read`, `public_request`, `public_track`). Requests need a signed form-time token and an empty honeypot field. Order tracking needs the order or receipt number plus a phone number whose last 7 digits match the customer's. Staff manage it on the **Website** page (`website.manage`; owners and managers): the request queue (create a pre-filled order, call/WhatsApp, decline) and the site details (switch on, headline, about, phone, WhatsApp, email, address, hours, map link). Products appear only when "Show this on the website" is ticked. Set `PUBLIC_SITE_ORGANIZATION_ID` when more than one organization has its website switched on.
- **Phones and installing**: below 760px wide the sidebar becomes a bottom bar (Overview, Sales, Orders, More) and list tables with an actions column turn into one card per row (`frontend/src/app/mobile.css`). The staff app (`/manifest.webmanifest`) and the public website (`/site/manifest.webmanifest`) are installable web apps with a pass-through service worker (`/sw.js`, caches nothing so figures are always live). Account menu → "Get the app on your phone" and Website → "Website QR code" show a QR code (generated in the browser with `qrcode`) that can be downloaded as a PNG or printed as an A4 poster.
- **Profile**: `PATCH /api/v1/auth/me/` lets a person edit their own first name, last name and email (audited as `user.profile_updated`). Username, role and access stay with administrators. The top-right account menu holds My profile, Change password, Messages, the USD/LRD display switch, business switching and Sign out.
- **Section/branch focus**: the top-bar selector sends `X-Section-ID` / `X-Branch-ID` on reads (GET). `focus_on_view` (`apps/identity/scope.py`) narrows `allowed_section_ids` / `allowed_branch_ids` to it, so every list, the dashboard, reports, exports and search follow it. A value outside the person's scope is ignored, writes always use the full scope, and alerts stay unfiltered. Use `allowed_section_ids(membership, full=True)` where the full scope is needed regardless of focus.
- Permission codes and starter roles live in `backend/apps/identity/access.py`. After editing them, run `python manage.py sync_access` to update existing organizations.

Provisional policy samples that can be revised are recorded in [discovery decisions](./docs/discovery-decisions.md).

## Production deployment

`deploy/` contains everything to run the system on one Linux server with Docker:
- **Caddy** for automatic HTTPS and security headers, serving the app;
- **Django/gunicorn** for the API;
- **PostgreSQL** for the database;
- a **backup** container for nightly checksummed backups of the database and uploads, kept for 30 days.

```sh
cp deploy/.env.example deploy/.env      # set SITE_DOMAIN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```
Then follow [the operator runbook](./docs/operations/runbook.md) for first-time setup, updates, backups, restores and monitoring. The owner's day-to-day guide is [the admin guide](./docs/onboarding/admin-guide.md); it covers importing the opening catalog with `manage.py import_catalog`. Before go-live, work through the [acceptance checklist](./docs/acceptance/acceptance-checklist.md) and the [owner sign-off](./docs/acceptance/owner-signoff.md).

Operational commands:
- `python manage.py verify_integrity`: checks that stock ledgers, payments, totals and stored files agree. It exits 1 on any mismatch.
- `python manage.py import_catalog --file products.csv --user <owner> [--dry-run]`: imports the opening catalog and stock, all or nothing.

## Documents

- [Product requirements (PRD)](./prd.md) — users, workflows, scope, acceptance criteria, and success measures.
- [02 User flows & UI/UX specification](./user-flows-ui-ux.md) — screen inventory, journey flows, interaction and accessibility guidance.
- [03 System architecture](./system-architecture.md) — application boundaries, deployment view, decisions, and critical sequences.
- [04 Database design (ERD)](./database-design-erd.md) — Mermaid ERD, entity definitions, constraints, and open decisions.
- [05 API specification](./api-specification.md) — REST resources, conventions, examples, and access rules.
- [06 Development task breakdown](./plan.md) — phased implementation tasks and PRD requirement traceability.
- [Technical requirements (TRD)](./trd.md) — implementation constraints, security, reliability, and delivery requirements.
- [Budgetary quotation](./quotation.md) — indicative development and operating costs, assumptions, and exclusions.
- [Requirements checklist](./requirements-checklist.md) — traceability and readiness checks for refinement and delivery.
- [Liberia provider and policy discovery](./provider-research.md) — preliminary provider evidence, pricing snapshot, and open verification/financial decisions.
- [Planning checkpoints](./checkpoints/) — requirement-to-plan and plan-to-task coverage.

## Proposed stack

- Frontend: React with TypeScript; responsive web application installable as a Progressive Web App (PWA).
- Backend: Python with Django and Django REST Framework.
- Database: PostgreSQL.

These are planning documents, not a binding commercial contract. Confirm country, currency, tax rules, and hosting region before MVP implementation; verify provider choices only before starting the deferred integration release.
