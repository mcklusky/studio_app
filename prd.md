# Product Requirements Document

## Business Management System for Clothing, Printing, and Photography

| Document status | Draft for review |
|---|---|
| Version | 1.0 |
| Date | 2026-11-24 |
| Product owner | Business owner (to be confirmed) |
| Related documents | [TRD](./trd.md), [User flows & UI/UX](./user-flows-ui-ux.md), [System architecture](./system-architecture.md), [ERD](./database-design-erd.md), [API specification](./api-specification.md), [Development task breakdown](./plan.md), [Quotation](./quotation.md), [Requirements checklist](./requirements-checklist.md) |

## 1. Executive summary

Build a simple, secure, mobile-friendly business management system for one owner to manage clothing, printing, and photography operations. Staff should be able to record sales, orders, stock, purchases, expenses, and payments from a phone or computer. Owners and managers should see trustworthy, combined or business-specific operational and financial reports.

The initial product is a responsive web application that can be installed as a PWA. It is not a native iOS/Android application and does not promise offline transaction entry. The planned implementation uses React, Django REST Framework, and PostgreSQL; see the [TRD](./trd.md).

## 2. Problem and opportunity

The businesses need one dependable place to replace scattered records and manual calculations. The product should reduce missed balances, stock discrepancies, delayed order follow-up, and time spent assembling management reports, while remaining approachable to staff without technical training.

## 3. Goals and non-goals

### Goals

- Record sales, purchases, expenses, payments, and custom orders consistently.
- Keep stock quantities and movement history accurate and explainable.
- Track customer and supplier balances, including partial payments.
- Support clothing, printing, and photography workflows without forcing them into one generic order form.
- Provide role-based access, attribution, audit history, and reliable backups.
- Work well on current Android and iPhone browsers and desktop browsers.
- Show separate business-section results and combined results for the same organization.
- Accept transactions in Liberian dollars (LRD) and United States dollars (USD), with an auditable exchange-rate snapshot and base-currency reporting.
- Support staff-entered records of payments received by cash, mobile money, bank, or card; live collection and automated customer messaging are deferred to a later release.

### Non-goals for the first release

- Native mobile apps or guaranteed offline transaction creation/synchronization.
- Full general-ledger accounting, payroll processing, tax filing, or statutory audit certification.
- Franchise licensing, unrelated third-party integrations, and multi-company statutory consolidation.

## 4. Users and access

| User | Primary needs |
|---|---|
| Owner / Admin | Configure the organization, users, business sections, and branches; oversee all records and reports. |
| Manager | Monitor sales, stock, orders, debts, expenses, and reports within assigned scope. |
| Cashier | Record sales and payments; issue receipts; view only the customer and transaction information needed for those tasks. |
| Inventory / Purchasing staff | Maintain products, receive purchases, record stock counts and adjustments, and manage suppliers. |
| Photographer | Manage assigned shoots, customer details needed for delivery, and photography order status. |
| Printing / Clothing staff | Update assigned jobs, production progress, and delivery information. |

Admins can grant permissions by role and business section. Each user has an individual account; shared staff logins are not supported.

## 5. Scope and release approach

### MVP (initial production release)

- Organization setup with Clothing, Printing, and Photography sections; optional branches.
- Authentication, staff accounts, roles, permissions, and audit history.
- LRD and USD transaction entry with exchange-rate snapshots and base-currency reporting.
- Dashboard with date-range and business-section filters.
- Customer and supplier records.
- Product/service catalog, stock tracking, purchase receiving, stock adjustments, and low-stock alerts.
- Sales, invoices/receipts, partial payments, balances, expenses, and supplier payments.
- Manual recording of customer and supplier payments, including cash, mobile money, bank transfer, and card payments collected outside the system.
- Printable/downloadable receipts that staff can share manually using device-supported sharing.
- Photography, printing, and clothing order workflows.
- Search and filters across common business records.
- Essential reports with PDF and spreadsheet export.
- Responsive interface, deployment, backup/restore procedure, and staff onboarding.

### Later releases / optional scope

- Live mobile-money/card/bank checkout and automated email/SMS/WhatsApp delivery of receipts, reminders, and order updates.
- Advanced accounting, tax integrations, payroll, loyalty, barcode scanning, advanced multi-currency consolidation, and native apps.
- Advanced offline workflows, forecasting, configurable approval chains, or custom report designer.

## 6. User scenarios and acceptance criteria

### US-01 — Record a sale and collect payment (Priority: P1)

As a cashier, I need to record a sale and issue a receipt so that the customer and business have an accurate transaction record.

**Acceptance scenarios**

1. **Given** an active product and available stock, **when** a cashier records quantity, price, discount, and payment, **then** the system calculates the total and balance, records the user and timestamp, and reduces stock in the same committed transaction.
2. **Given** a sale is partly paid, **when** the cashier records another payment, **then** the payment history and remaining balance update without changing the original sale lines.
3. **Given** a completed sale, **when** the cashier chooses a receipt action, **then** the system provides a printable/downloadable receipt that can be shared from the device.
4. **Given** a sale would take tracked stock below zero, **when** it is submitted, **then** it is blocked unless an authorized user explicitly allows the configured exception; the decision is audited.

### US-02 — Maintain inventory and receive purchases (Priority: P1)

As inventory staff, I need stock to change through traceable events so that on-hand quantities can be reconciled.

**Acceptance scenarios**

1. **Given** an approved purchase is marked received, **when** receiving is confirmed, **then** received quantities are added once and a stock movement references the purchase.
2. **Given** stock reaches or falls below its configured minimum, **when** inventory is viewed, **then** the product appears in low-stock results and an in-app alert is available.
3. **Given** an authorized count, damage, loss, return, or correction, **when** an adjustment is posted with a reason, **then** on-hand stock and the movement history show the adjustment and its actor.

### US-03 — Manage customers, suppliers, and debts (Priority: P1)

As an owner or cashier, I need customer and supplier balances with payment history so that I can follow up on amounts due.

**Acceptance scenarios**

1. **Given** an invoice has a balance, **when** a customer payment is recorded, **then** the balance decreases by the payment amount and the payment, method, date, and recorder are visible.
2. **Given** a received purchase is not fully paid, **when** a supplier payment is recorded, **then** the supplier balance decreases and remains traceable to that purchase.
3. **Given** a record has an outstanding balance, **when** a user filters by payment status, **then** only matching due, partially paid, or paid records are returned.

### US-04 — Manage custom orders (Priority: P1)

As a department staff member, I need a workflow specific to the work I deliver so that specifications, deposits, due dates, and progress are not lost.

**Acceptance scenarios**

1. **Given** a photography booking, **when** staff record the customer, shoot type/package, shoot date, price, photographer, and notes, **then** the booking has a trackable payment balance and delivery status.
2. **Given** a printing job, **when** staff record product/service, quantity, dimensions, design, price, cost, and due date, **then** its status can progress through Pending, Designing, Production, Completed, and Delivered.
3. **Given** a custom clothing/jersey job, **when** staff record size, color, quantity, design, custom name/number, deposit, and due date, **then** those specifications remain attached to the order throughout production.
4. **Given** an order has a due date or pending status, **when** its due date is approaching or status is overdue, **then** authorized users can find it through the dashboard or order filters.

### US-05 — Review business performance (Priority: P1)

As an owner, I need timely operational and financial summaries so that I can make informed decisions.

**Acceptance scenarios**

1. **Given** transactions exist, **when** an owner selects a date range and business section, **then** dashboard totals and report rows use the same filters and clearly state the period and section.
2. **Given** a user exports a report, **when** PDF or spreadsheet export is selected, **then** the generated file reflects the selected filters and includes a generation date.
3. **Given** an owner switches from a business section to combined view, **when** the dashboard refreshes, **then** totals include only the selected organization’s permitted sections and do not duplicate transactions.

### US-06 — Control staff access and preserve accountability (Priority: P1)

As an admin, I need individual accounts and permission controls so that staff see only the functions and business data they need.

**Acceptance scenarios**

1. **Given** a user lacks a permission, **when** they attempt the restricted action through the interface or API, **then** the action is denied.
2. **Given** a user creates or changes a financial, stock, customer, supplier, or order record, **when** the change is saved, **then** the audit history records the actor, time, action, and affected record.
3. **Given** a staff account is deactivated, **when** that user next attempts to access the system, **then** access is denied and historical attribution remains intact.

### US-07 — Find records and act on alerts (Priority: P2)

As staff, I need fast search and useful reminders so that I can find records and follow up on operational work.

**Acceptance scenarios**

1. **Given** records exist, **when** a user searches by customer, product, supplier, invoice/order number, staff, date, or payment status, **then** matching authorized records are shown.
2. **Given** low/out-of-stock items, unpaid balances, or upcoming/pending orders exist, **when** a user opens alerts, **then** relevant items link to their records and respect the user's permissions.

## 7. Functional requirements

Each requirement is independently testable. Priorities: **MVP** means required for initial release; **Later** means explicitly deferred.

### Organization, users, and dashboard

- **REQ-001 (MVP):** The system MUST support an organization containing separate Clothing, Printing, and Photography business sections, with optional branches and a combined view.
- **REQ-002 (MVP):** Admins MUST be able to create, deactivate, and assign staff accounts, roles, permissions, and business-section/branch scope.
- **REQ-003 (MVP):** The dashboard MUST show sales for the current day, week, month, and selected period; expenses; purchases; gross/net profit; customer balances; supplier balances; stock value; low-stock items; and recent transactions.
- **REQ-004 (MVP):** Dashboard values MUST support filtering by date range, business section, and branch; combined totals MUST include each eligible transaction once.
- **REQ-005 (MVP):** Financial totals MUST identify transaction and base currency, period, and exchange-rate basis, and distinguish sales, cash collected, purchases, expenses, gross profit, and net profit.

### Sales, payments, customers, and suppliers

- **REQ-006 (MVP):** Authorized users MUST be able to record a sale with customer, line items, quantity, unit price, discount, timestamp, staff attribution, payment method, and optional notes.
- **REQ-007 (MVP):** The system MUST calculate line totals, invoice total, paid amount, and outstanding balance using decimal-safe monetary arithmetic and configured rounding.
- **REQ-008 (MVP):** The system MUST support partial and multiple customer payments, record payment dates/methods/actors, and prevent overpayment unless explicitly configured as customer credit.
- **REQ-009 (MVP):** Users MUST be able to print or download a customer receipt/invoice and share the file using device-supported sharing.
- **REQ-010 (MVP):** The system MUST support customer and supplier profiles, contact details, location, notes, transaction history, and outstanding balances.
- **REQ-011 (MVP):** Supplier purchases MUST support partial payments, payment history, purchase references, and a remaining amount owed.
- **REQ-012 (MVP):** Financial transactions MUST be voided or corrected through an authorized, reasoned reversal; posted financial history MUST NOT be silently overwritten or deleted.

### Catalog, inventory, purchasing, and expenses

- **REQ-013 (MVP):** Products/services MUST support name, category, image, SKU, size/color variants where applicable, buying/selling prices, supplier, status, and optional stock tracking.
- **REQ-014 (MVP):** The system MUST adjust tracked inventory atomically when a sale is posted and MUST identify the sale in the stock movement history.
- **REQ-015 (MVP):** The system MUST record purchases with supplier, lines, quantities, unit cost, shipping/other costs, reference, date, payment, and receiving status.
- **REQ-016 (MVP):** Inventory MUST increase only for quantities explicitly received; duplicate receiving MUST be prevented or reversed with an audited correction.
- **REQ-017 (MVP):** Authorized users MUST record reasoned stock movements for opening balance, count correction, damage, loss, return, and other approved adjustments.
- **REQ-018 (MVP):** Products MUST support configurable minimum stock thresholds and views for low-stock and out-of-stock products.
- **REQ-019 (MVP):** The system MUST record expenses with category, description, amount, date, payment method, recorder, and optional receipt/photo attachment.
- **REQ-020 (MVP):** The system MUST show inventory valuation and identify the valuation basis used; the initial recommended basis is moving weighted-average cost.

### Department orders

- **REQ-021 (MVP):** Photography orders MUST support customer, shoot type/package, shoot date, price, payments/balance, assigned photographer, delivery status, phone, and notes.
- **REQ-022 (MVP):** Printing orders MUST support customer, service/product, quantity, size, design/specification, production cost, selling price, payments/balance, responsible staff, due date, and defined production status.
- **REQ-023 (MVP):** Clothing/custom jersey orders MUST support customer, product, size, color, quantity, design, custom name/number, production cost, selling price, deposit/balance, responsible staff, due date, and order status.
- **REQ-024 (MVP):** Order status changes MUST be permission-checked and attributed; authorized users MUST be able to correct a status with an audit record.
- **REQ-025 (MVP):** Department orders MUST be searchable and reportable separately; they MUST NOT decrement stock unless linked stock items/material consumption are explicitly configured.

### Search, notifications, and reporting

- **REQ-026 (MVP):** Users MUST be able to search and filter authorized records by customer, product, supplier, invoice/order number, date, staff, business section, branch, and payment status.
- **REQ-027 (MVP):** In-app alerts MUST identify low/out-of-stock products, customer/supplier balances, upcoming delivery dates, and pending or overdue orders.
- **REQ-028 (MVP):** Reports MUST include daily/weekly/monthly/yearly and selected-period sales, expenses, purchases, gross/net profit, best-selling products, best customers, inventory value, and customer/supplier debts.
- **REQ-029 (MVP):** Authorized users MUST be able to export filtered reports as PDF and a spreadsheet-compatible file.
- **REQ-030 (Later):** With customer consent and configured provider accounts, the system MUST send approved receipts, payment reminders, and order updates through enabled email, SMS, and WhatsApp channels, and record delivery status and failures.

### Security, backup, usability

- **REQ-031 (MVP):** All users MUST authenticate with individual accounts; permissions MUST be enforced server-side for both interface and API requests.
- **REQ-032 (MVP):** The system MUST retain an audit history of significant create, update, reverse, permission, and authentication events, including actor and timestamp.
- **REQ-033 (MVP):** Database and uploaded attachments MUST be backed up on a defined schedule, encrypted in transit and at rest where supported, and recoverable through a documented restore procedure.
- **REQ-034 (MVP):** The interface MUST be responsive and usable on supported current Android, iOS, Windows, and macOS browsers.
- **REQ-035 (MVP):** Forms MUST validate required fields, explain errors in plain language, preserve entered values after recoverable validation failures, and confirm destructive or irreversible actions.
- **REQ-036 (Later):** The system MAY support transaction entry while offline after a separate design for conflict resolution and reconciliation is approved.
- **REQ-037 (MVP):** Users MUST be able to choose LRD or USD separately for each eligible transaction, and transactions in both currencies MUST coexist in the same organization and reporting period. The system MUST preserve each original amount and approved FX snapshot, use USD as the reporting base, show original-currency subtotals separately, and convert consolidated totals to USD.
- **REQ-038 (Later):** The system MUST support configured mobile-money and card/bank payment providers through server-created payment intents and authenticated provider callbacks; payment state MUST be idempotent, auditable, reconcilable, and remain pending until provider confirmation. MVP payments are recorded manually after being received outside the system.

## 8. Business rules and definitions

- **Sales** are posted customer invoices/orders recognized as sales; **cash collected** is the sum of recorded payments. These measures are shown separately.
- **Customer balance** is posted receivables less applied payments and credits. **Supplier balance** is received purchase obligations less applied payments and credits.
- **Gross profit** is net sales less cost of goods sold for tracked inventory. **Net profit** is gross profit less recorded operating expenses. Tax treatment and statutory accounting are outside MVP scope.
- Purchases of inventory are not counted as an operating expense at purchase time; cost enters gross profit when the goods are sold. Shipping and other landed costs are allocated to inventory cost according to the agreed accounting policy.
- Initial stock valuation recommendation: moving weighted-average cost. The owner/accountant must approve this policy before launch.
- A stock-tracked sale and its stock movement commit together. Corrections use reversal/adjustment records, not silent edits to posted history.
- Order deposits are recorded as payments against the order. The MVP's reporting policy for uncompleted custom orders must be confirmed with the business accountant before financial reports are treated as official.
- This organization's reporting base currency is USD; each eligible transaction independently uses LRD or USD, and both currencies may be used concurrently. The system does not use a system-wide currency mode. Each transaction stores its original amount, currency, exchange rate, rate timestamp/source, and converted USD amount. Reports show separate LRD/USD subtotals and a consolidated USD total, disclosing the conversion basis. Owner-selected provisional policy: an authorized owner/admin enters the daily rate. The accountant must confirm the rate source, effective-time rule, rounding, and accounting treatment before launch.
- USD is the configured reporting base currency and is locked after the first posted financial transaction unless an audited conversion/migration is approved.
- Tax rates and invoice labels are configurable; the business owner is responsible for confirming local legal/tax requirements.
- MVP does not send automated external messages or initiate/confirm online payments. Staff can print, download, or manually share receipts and record payments received through external channels.
- Later provider-based payments may be considered settled only after provider-authenticated confirmation; browser redirects alone are not proof of payment.
- Product catalog prices use the organization base currency by default; a sale in the other currency uses the approved rate snapshot and displays the converted price before confirmation. Cross-currency payment allocations require an explicit conversion snapshot.

## 9. Key product entities

MVP entities include organization, business section, branch, user, role/permission, customer, supplier, product/service, product variant, exchange rate, stock balance, stock movement, sale/invoice, sale line, purchase/receipt, expense, manually recorded payment/allocation, custom order, order status history, attachment, notification, report export, and audit event. Provider payment intents/events and messaging consent/outbox/delivery entities are deferred with their integrations.

## 10. Non-functional requirements

- **NFR-01 — Usability:** A first-time cashier should be able to complete a standard sale after brief onboarding without technical assistance.
- **NFR-02 — Responsiveness:** Common list/search views should provide results within 2 seconds at the agreed MVP dataset and normal network conditions; dashboard summary within 3 seconds.
- **NFR-03 — Availability:** Target at least 99.5% monthly application availability excluding announced maintenance, subject to chosen hosting plan.
- **NFR-04 — Capacity:** Initial sizing should support 25 concurrent users and 100,000 transaction/order records per organization, with a documented path to scale.
- **NFR-05 — Accessibility:** Core workflows should support keyboard navigation, readable contrast, labels, and mobile touch targets, targeting WCAG 2.2 AA.
- **NFR-06 — Security:** Use TLS, secure password storage, least privilege, protected sessions, input validation, rate limiting for authentication, and dependency/security updates.
- **NFR-07 — Recovery:** Target RPO of 24 hours and RTO of 8 business hours for the initial hosted release; verify restoration at least quarterly.
- **NFR-08 — Data integrity:** Monetary arithmetic MUST use decimal values, inventory updates MUST be transactional, and concurrent stock sales MUST not produce negative/inconsistent quantities.
- **NFR-09 — Privacy:** Collect only business-required personal data, restrict access by role, and define retention/export/deletion processes appropriate to local law.
- **NFR-10 — Browser support:** Support the latest two major versions of Chrome, Safari, Edge, and Firefox where practical.

## 11. Success measures

- **SC-001:** At least 95% of sampled sales, purchases, and adjustments have complete actor, timestamp, and reference information after the first month.
- **SC-002:** Staff can complete a standard sale and issue a receipt in under 2 minutes after onboarding.
- **SC-003:** A user can locate an invoice or order by its number in under 10 seconds.
- **SC-004:** Daily sales, outstanding balances, and tracked stock values reconcile to the underlying records with no unexplained variance in acceptance testing.
- **SC-005:** At least 90% of a representative staff group can complete their assigned top three workflows without coaching after onboarding.
- **SC-006:** A full database restore is demonstrated successfully before production handover and at least quarterly thereafter.
- **SC-007:** A reporting period containing both LRD and USD transactions shows correct separate subtotals and a reconciled USD consolidated total; each transaction retains its original amount and approved FX snapshot.
- **SC-008:** Every manually recorded payment is attributed to a staff member and reconciles to the related balance; receipts can be printed, downloaded, or manually shared after posting.

## 12. Assumptions, dependencies, and risks

- Confirmed from owner: one physical location; customers and suppliers are shared; stock and reports remain filterable by business section; no legacy data import is planned.
- Confirmed from owner: transaction currencies are LRD and USD. MVP uses manual recording for payments collected outside the system; live payment collection and automated email/SMS/WhatsApp integrations are deferred to a later release.
- The owner will supply business name/logo, product and opening stock data, staff/roles, expense categories, receipt wording, time zone, tax requirements, and hosting region.
- Product catalog import depends on the quality and format of existing records; data cleanup may be separately estimated.
- Payment and messaging provider names are not selected. Their Liberia availability, merchant eligibility, currency support, webhook capability, fees, and terms must be verified before estimating a future integration phase; this does not block the manual-payment MVP.
- The owner/accountant must approve the profit, inventory valuation, tax, and custom-order deposit reporting rules before financial sign-off.
- Risks include incorrect opening stock, staff sharing accounts, unclear tax/exchange-rate/accounting rules, internet outages, future provider outages or duplicate callbacks, and unauthorized access to customer data. Mitigate with onboarding, individual accounts, audit history, suitable future integration controls, backup/restore drills, and explicit financial reconciliation.

## 13. Open decisions for discovery

1. Confirm time zone, tax/VAT rules, invoice fields, and accountant approval of the owner/admin-entered daily exchange-rate source/effective-time policy; USD is the configured reporting base.
2. Before a later integration phase, select payment and messaging providers and verify Liberia onboarding, LRD/USD support, callback/webhook security, fees, consent, and message-template requirements.
3. Confirm expected number of users and transaction volume.
4. Confirm hosting region preference (Liberia requested; a nearby supported region may be necessary) and owner control of cloud/domain/provider accounts.
5. Confirm the accountant-approved treatment of deposits, discounts, returns, inventory costs, FX gains/losses, and payment-provider fees.

## 14. Confirmed discovery decisions

- **Location:** Liberia.
- **Currencies:** accept both LRD and USD; use USD as the reporting base currency.
- **Operations:** one location; share customer and supplier records; keep stock and reports filterable by business section.
- **Payments and communications:** MVP records payments manually after external collection; receipts may be printed, downloaded, or manually shared. Live payment-provider and automated messaging integrations are deferred to a later release.
- **Data migration:** none planned; products/opening stock and required setup data will be entered as initial configuration.
- **Provisional financial settings:** owner/admin enters a daily FX rate; moving weighted-average inventory costing is the selected MVP starting point. Both require accountant approval, including the rate source/effective-time rule and related accounting treatment.
- **Still unconfirmed:** tax/invoice requirements, accountant decisions for deposits/refunds/fees/FX differences, payment/messaging providers and merchant accounts, and expected users/transaction volume.
- **Accounting policy:** not confirmed; production financial reporting remains subject to owner/accountant approval.

Do not treat unresolved items as approved assumptions in a production financial workflow.
