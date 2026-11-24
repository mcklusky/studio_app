# Release acceptance checklist (T085)

Status as of 24 Nov 2026, the first production-stack trial on a development PC. Each item is ✅ verified, 🟡 partly verified, or ⬜ to do before go-live. "Automated" means it is covered by the backend test suite: `python manage.py test`, 156 tests, run on PostgreSQL 17 in CI (`.github/workflows/ci.yml`) on every push.

## Security and access

| Check | How verified | Status |
|---|---|---|
| Every API action is permission-checked server-side; a missing permission code is denied by default | Automated (identity, sales, orders, payments, reports, files tests) | ✅ |
| Organization isolation: no record of another organization can be read or changed | Automated (`test_access`, search, files) | ✅ |
| Section/branch scope respected in lists, search, alerts, reports and downloads | Automated | ✅ |
| Deactivated staff are signed out at once and cannot sign in; history keeps their name | Automated (`test_staff`) | ✅ |
| Last owner/admin cannot be removed; nobody can promote or demote themselves | Automated | ✅ |
| Login rate-limited (5/minute); passwords meet the strength checks | Automated | ✅ |
| Production settings refuse to start without a real secret key and domain | `manage.py check --deploy`; startup guard | ✅ |
| HTTPS with automatic redirect; HSTS, CSP, X-Frame-Options, nosniff, Referrer-Policy sent | Production-stack trial (curl) | ✅ |
| No third-party requests from the browser (fonts are bundled) | Production-stack trial: no external resource loaded | ✅ |
| Database not reachable from outside the server | No published port in `docker-compose.prod.yml` | ✅ |
| No known vulnerabilities in dependencies; no secrets in git history | `pip-audit`, `npm audit`, gitleaks in CI, weekly (`security.yml`); Dependabot | ✅ |
| HSTS raised to one year after go-live | Change `HSTS_SECONDS` | ⬜ |

## Uploads

| Check | How verified | Status |
|---|---|---|
| Type decided from file content; disguised files rejected | Automated (`apps/files/tests.py`) | ✅ |
| Photos re-encoded, resized, GPS/camera metadata removed | Automated + manual (1500×2000 → 1200×1600, no EXIF) | ✅ |
| Private storage, random names, download checks permission and scope | Automated | ✅ |
| Size limit (8 MB app, 12 MB proxy) | Automated | ✅ |

## Data integrity and recovery

| Check | How verified | Status |
|---|---|---|
| Stock ledger = balances; payments = allocations; sale totals = lines | `verify_integrity` + automated | ✅ |
| Simultaneous requests: last unit sold once, a balance cannot be paid twice, receipt numbers unique | Automated on PostgreSQL (`apps/inventory/tests/test_concurrency.py`) | ✅ |
| Reports reconcile with hand-worked books; sections add up to combined | Automated (`apps/reports/tests`) | ✅ |
| Nightly backup runs, has checksums, keeps 30 days | Production-stack trial | ✅ |
| Restore drill: backup → change → restore → `verify_integrity` passes, change gone | Production-stack trial | ✅ |
| Off-site backup copy arranged | Owner/operator decision (runbook §4) | ⬜ |
| First monthly restore drill on the real server, recorded in the runbook | After go-live | ⬜ |

## Usability and accessibility

| Check | How verified | Status |
|---|---|---|
| All pages, forms and dialogs: every field labelled, every button named, images have alt text, one H1 per page | Automated scan in headless Edge (all 11 pages + order form + checkout): no issues | ✅ |
| Keyboard: dialogs close with Esc (innermost first), search with `/` and arrows, focus visible | Manual | 🟡 Spot-checked. Full keyboard-only run-through to do |
| Phone layout (390 px): every page usable, tables collapse, dialogs fit | Screenshots of every new screen | 🟡 Checked in emulation. Test on 2 real staff phones (Android + iPhone) |
| Colour contrast: yellow is never used as text on white (olive accent instead) | Design rule | 🟡 Run a contrast checker on the final brand colours |
| Screen reader smoke test (NVDA or TalkBack): sign in, record a sale | | ⬜ |

## Performance

| Check | How verified | Status |
|---|---|---|
| Lists paginated (max 200); search returns ≤ 5 per group; exports capped at 500 rows | Code + automated | ✅ |
| App bundle ~116 KB gzipped JS; fonts and static files cached | Build output; Caddy cache headers | ✅ |
| Realistic volume test: 1 year of sales (~20k), dashboard and reports under 2 s on the production server | | ⬜ Run on the real server with generated data before go-live |
| Works acceptably on a slow mobile connection (Chrome "Slow 4G") | | ⬜ |

## Go-live tasks (operator)

| Task | Status |
|---|---|
| Server, domain, DNS, `deploy/.env` with fresh secrets | ⬜ |
| Owner account and organization created (runbook §2) | ⬜ |
| Opening catalog/stock imported and spot-counted | ⬜ |
| Staff accounts created; each signs in and changes their password | ⬜ |
| Uptime monitor on `/api/v1/health/ready/`; error emails configured | ⬜ |
| Owner sign-off on business rules ([owner-signoff.md](./owner-signoff.md)) | ⬜ |
