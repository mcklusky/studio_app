# Requirements and Delivery Checklist

Use this as a refinement and acceptance aid alongside the [PRD](./prd.md), [TRD](./trd.md), [UI/UX specification](./user-flows-ui-ux.md), [architecture](./system-architecture.md), [ERD](./database-design-erd.md), [API specification](./api-specification.md), and [development task breakdown](./plan.md). Items are unchecked because implementation and stakeholder approval have not started.

## Product scope and decisions

- [x] Confirm location is Liberia, both LRD and USD are required, one physical location is planned, customers/suppliers are shared, stock/reports are section-filterable, and no legacy import is planned.
- [x] Set USD as the reporting base currency while accepting LRD and USD transactions.
- [ ] Confirm time zone, tax/invoice requirements, and accountant approval of the owner/admin-entered daily FX rate source and effective-time rule.
- [ ] Confirm user count, role matrix, and initial transaction volume.
- [ ] Owner selected moving weighted-average inventory costing; accountant approval and treatment of discounts, refunds, deposits, landed costs, and profit reporting are still required.
- [x] Confirm manual payment recording for MVP; defer live payment collection and automated email/SMS/WhatsApp integrations to a later release.
- [ ] Before later integrations, select and verify Liberia-supported payment and messaging providers, merchant eligibility, LRD/USD support, fees, sandbox, callback, sender/template, and consent requirements. Preliminary public-source findings are in [provider research](./provider-research.md); provider selection remains open.
- [ ] Confirm opening setup data for products, stock, users, and expense categories; no legacy transaction import is planned.

## Requirement traceability

- [ ] REQ-001–REQ-005: organization setup and dashboard validated.
- [ ] REQ-006–REQ-012: sales, receipts, customer balances, supplier balances, payments, and reversals validated.
- [ ] REQ-013–REQ-020: catalog, inventory, receiving, adjustments, expenses, and valuation validated.
- [ ] REQ-021–REQ-025: photography, printing, clothing workflows, status history, and stock behavior validated.
- [ ] REQ-026–REQ-030: search, alerts, reports, exports, and later-release customer communications validated.
- [ ] REQ-031–REQ-038: authentication, authorization, audit, backup, responsive usability, deferred offline scope, multi-currency, and later-release payment-provider flows validated.

## Acceptance and operational readiness

- [ ] Cashier completes a standard sale and shares a receipt in under two minutes.
- [ ] Partial customer and supplier payments recalculate balances correctly.
- [ ] LRD and USD transactions can coexist in one reporting period, retain original amounts/FX snapshots, and reconcile as separate subtotals plus a consolidated USD total.
- [ ] Manual payments record the method, amount, date, staff actor, and allocation; balances reconcile after partial payments.
- [ ] (Later release) Payment callbacks are signature-verified and idempotent; redirects alone cannot settle a payment.
- [ ] (Later release) Email/SMS/WhatsApp sends honor current customer consent and expose delivery/failure state.
- [ ] Sale, purchase receipt, adjustment, and reversal preserve stock and audit history.
- [ ] Concurrent sale tests do not cause unintended overselling or duplicate postings.
- [ ] Business-section and combined reports reconcile without duplicate transactions.
- [ ] PDF and spreadsheet exports match the selected date, section, and branch filters.
- [ ] Role and organization/branch isolation tests deny unauthorized access at the API boundary.
- [ ] Mobile and desktop critical workflows pass usability and accessibility review.
- [ ] Production backup and restore are demonstrated; recovery objectives are documented.
- [ ] Owner approves financial definitions, receipt content, permissions, and production data import.
- [ ] Owner/accountant approves FX rate source, tax, inventory costing, and deposit/return policies; USD base currency is confirmed.
- [ ] Provider onboarding, supported currencies, messaging sender/templates, settlement reconciliation, and fees are verified before a later integrated release.
- [ ] Source code, any configured third-party accounts, data export, deployment guide, admin guide, and support terms are handed over.

## Requirements quality review

- [ ] PRD requirements use unique, sequential `REQ-XXX` identifiers.
- [ ] Acceptance scenarios are observable and testable.
- [ ] MVP and later-release boundaries are explicit.
- [ ] Risks, assumptions, success measures, and unresolved owner decisions are documented.
- [ ] TRD design choices map to product requirements and have security, integrity, and recovery coverage.
- [ ] UI/UX, architecture, ERD, API, and task breakdown are reviewed against the same approved product decisions.
- [ ] All task breakdown plan items have tasks and all PRD requirement IDs have an explicit implementation or deferral mapping.
