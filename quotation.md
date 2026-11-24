# Budgetary Quotation

## Business Management System

| Quote status | Indicative estimate — not a binding offer |
|---|---|
| Estimate date | 2026-11-24 |
| Currency | USD; local-currency conversion and applicable taxes are not included |
| Scope basis | Revised MVP: Liberia, LRD/USD transactions, manual payment recording; live integrations deferred |
| Validity | Reconfirm after accountant policy approval and detailed discovery |

## 1. Development estimate

| Work package | Estimate |
|---|---:|
| Discovery, workflow confirmation, and requirements refinement | $2,000 |
| UX/UI design and responsive prototypes | $2,000 |
| React/TypeScript web application | $4,000 |
| Django/DRF backend, permissions, and PostgreSQL data layer | $5,000 |
| Sales, stock, purchases, expenses, payments, and department workflows | $4,500 |
| Reporting, export, audit, backup setup, and deployment | $2,500 |
| QA, acceptance support, handover documentation, and training | $2,000 |
| **Previously estimated base MVP (without currency conversion or live integrations)** | **$22,000** |

### Revised manual-payment MVP estimate

| Added work package | Planning range |
|---|---:|
| LRD/USD support, approved exchange-rate snapshots, base-currency reporting | $3,000–$5,000 |
| **Estimated MVP additions** | **$3,000–$5,000** |
| **Revised manual-payment MVP planning range** | **$25,000–$27,000** |

This planning range assumes the previous $22,000 base estimate covers manual payment recording and receipt printing/download/sharing. It excludes all live payment processing and automated messaging. Provider onboarding, compatibility, LRD/USD support, and fees in Liberia remain unverified and are not MVP gates.

**Timeline:** Re-estimate the schedule against the revised manual-payment scope before kickoff. The prior 20–30-week estimate included live integrations and should not be used as the schedule for this MVP.

The $25,000–$27,000 range is an indicative planning estimate, not a binding fixed-price offer. A signed statement of work should follow accountant approval and confirm milestones, acceptance, payment schedule, warranty/support, change control, and applicable taxes. A 15–25% contingency remains prudent.

### Deferred integration budget (not in MVP)

| Future work package | Previous planning range |
|---|---:|
| Mobile-money and card/bank provider checkout, callbacks, reconciliation | $5,000–$11,000 |
| WhatsApp, SMS, and email delivery, consent/preferences, templates, retries | $4,000–$8,000 |
| Provider-specific QA, security, settlement and delivery acceptance | $2,000–$4,000 |
| **Indicative future integration work** | **$11,000–$23,000** |

These are not included in the MVP total and must be re-estimated after provider verification.

## 2. Recurring and third-party costs

| Item | Indicative cost | Notes |
|---|---:|---|
| Hosting and managed application/database/worker services | $75–$300/month | Early-stage estimate; depends on supported region, traffic, storage, worker capacity, availability, and support tier. Liberia-hosted services may be unavailable; obtain approval before selecting a nearby region. |
| Domain registration | $15–$35/year | Domain extension and registrar vary; domain should be registered to the business owner. |
| Automated database backup / retained storage | $10–$40/month | May be bundled into managed database hosting; confirm retention and point-in-time recovery pricing. |
| Maintenance and security updates | Reconfirm after scope | The earlier $500–$1,000/month planning range assumed the integrated scope and is not a confirmed quote for this revised MVP. |
| Email/SMS/WhatsApp delivery | Not incurred in MVP | Automated messaging is deferred; provider, usage, sender, and template costs apply only if added later. |
| Payment gateway / mobile-money provider | Not incurred in MVP | Payments are recorded manually after external collection; provider setup and transaction fees apply only if added later. |
| Backups of uploaded media | Approximately $5–$30/month initially | Depends on attachment volume, retention, and storage/egress pricing; may be included in hosting. |

Cloud and communication charges are paid to the relevant providers and may change. These figures are budgeting ranges, not provider quotations.

**Public pricing check (2026-11-24):** Twilio lists Liberia outbound SMS at US$0.2677 per segment, before possible carrier fees, and WhatsApp at US$0.005 per message plus applicable Meta charges. These are provider-published snapshots, not selected-provider quotes; see [provider research](./provider-research.md). Local delivery, merchant eligibility, sender approval, and current fees still require confirmation.

## 3. Included in the MVP estimate

- Responsive React/TypeScript web app for supported Android/iOS and desktop browsers.
- Organization with Clothing, Printing, and Photography sections; basic branch support.
- Concurrent LRD and USD transaction entry, exchange-rate snapshots, separate original-currency subtotals, and consolidated reporting in USD.
- Individual staff accounts, role-based permissions, and audit history.
- Dashboard, sales/receipts, partial payments, customer/supplier records and balances.
- Product catalog, tracked inventory, purchases/receiving, stock adjustments, and alerts.
- Expense capture and attachments.
- Photography, printing, and clothing order workflows and status tracking.
- Manual recording of cash, mobile-money, bank-transfer, and card payments collected outside the system, with partial payment history and balance tracking.
- Receipts available for print, download, or manual device-supported sharing; no automatic sending in MVP.
- Search/filtering and core reports with PDF and spreadsheet-compatible export.
- Initial production deployment, automated database backup configuration, restore demonstration, admin guide, source-code handover, and agreed staff training.

## 4. Not included unless added to the statement of work

- Native iOS/Android applications or offline transaction synchronization.
- Live mobile-money/card/bank checkout, provider callbacks/reconciliation, and automated email/SMS/WhatsApp delivery (deferred; estimate separately).
- Additional providers, provider-specific features not listed in the signed scope, and unsupported payment rails.
- Payroll, full accounting ledger, tax filing, statutory/compliance certification, or legal/accounting advice.
- Advanced multi-company accounting consolidation or franchise features.
- Barcode hardware, POS terminals, printers, scanners, or physical equipment.
- Migration/cleanup of large or poor-quality legacy datasets beyond an agreed import allowance.
- Custom analytics, advanced approval workflows, major new modules, or third-party licenses.
- Provider fees, cloud taxes, domain renewals, payment processing, and messaging charges.

## 5. Ownership and handover

Subject to the final contract and full payment:

- The business should receive the project source code, deployment/configuration documentation, and export of its business data in standard formats.
- The business should own and control the domain and cloud-provider accounts. Cloud credentials must not be shared in this document; use named accounts and secure handover.
- The business owns its business data and should be able to obtain database backups and a data export.
- Third-party libraries and services remain subject to their own open-source licenses or provider terms; the business does not acquire ownership of those products.
- Contract terms should define any pre-existing reusable components, warranty period, and source-code transfer timing.

## 6. Future updates and changes

- Routine maintenance: confirm a separate monthly amount after the revised manual-payment scope, hosting, support hours, and response targets are agreed. The previous **$500–$1,000/month** range assumed the integrated scope and is not a quote for this MVP.
- Enhancements: estimate separately after requirements are approved. A planning rate of **$50–$100 per engineering hour** may be used for budgeting only; confirm actual vendor/team rate and minimums.
- New provider integrations, native apps, offline synchronization, advanced accounting, or major scope changes require a separate estimate.

## 7. Pricing assumptions and next steps

This estimate assumes one Liberia-based organization, one physical location, shared customer/supplier records, section-filtered stock/reports, three business sections, no legacy data import, up to approximately 25 concurrent users (unconfirmed planning assumption), LRD and USD transaction currencies with USD reporting base, one primary language, standard report layouts, and manual payment recording. The owner selected owner/admin-entered daily FX rates and moving weighted-average inventory costing as provisional settings; accountant approval is pending. Tax compliance and data residency remain unverified. Provider onboarding and fees are deferred to a later integration estimate.

Before signing a fixed quote, confirm:

1. Approve tax, invoice fields, time zone, and the daily exchange-rate source/effective-time rule; USD is the selected reporting base.
2. Approve moving weighted-average costing and accounting treatment for FX differences, refunds, and deposits.
3. Confirm number of users, exact section-level stock behavior, and owner-controlled hosting/domain accounts.
4. Agree delivery milestones, acceptance criteria, payment schedule, warranty, and change-request rates.
5. Before a later integration release, verify provider merchant onboarding, sandbox access, transaction and settlement currencies, fees, message consent, and sender/template requirements; see [provider research](./provider-research.md).
