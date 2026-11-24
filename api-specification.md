# 05 API Specification

## Business Management System — REST API

| Status | Draft 1.0 |
|---|---|
| Date | 2026-11-24 |
| Product requirements | [PRD](./prd.md) |
| Technical requirements | [TRD](./trd.md) |
| Data model | [ERD](./database-design-erd.md) |

This contract describes the MVP API shape. Customer/supplier payments are recorded manually after being received outside the system. Live provider and automated messaging endpoints below are explicitly deferred and are not part of the MVP API. Confirm exact field validation, tax behavior, currency precision, and status vocabularies during implementation.

## 1. Contract conventions

- Base path: `/api/v1/`; JSON over HTTPS.
- Browser authentication: server-side session using secure, HttpOnly, SameSite cookies and CSRF protection. Login, logout, and write requests require CSRF handling.
- Every resource is scoped to the authenticated user's organization and assigned section/branch. Clients cannot select another tenant by changing an ID.
- Use UUID resource IDs and human-readable, organization-scoped invoice/order numbers.
- Timestamps use ISO-8601 UTC strings. Currency amounts use decimal strings, e.g. `"125.50"`; never JavaScript floating-point totals as the source of truth.
- Each transaction independently uses `LRD` or `USD`; the currencies may coexist in the same organization and reporting period. Every posted monetary record includes its original amount/currency plus `base_currency`, `fx_rate_to_base`, `fx_rate_at`, and `base_amount`; USD transactions use rate `1`.
- The server calculates totals and validates prices, discounts, stock, permissions, and payment allocation.
- Collection responses are paginated; `page` and `page_size` are bounded. Filtering and sort fields are allowlisted.
- For retryable posting/receiving/payment operations, accept `Idempotency-Key`. Reusing a key with the same request returns the original result; a different request returns conflict.

## 2. Common response shapes

### Paginated list

```json
{
  "count": 42,
  "next": "/api/v1/sales?page=2",
  "previous": null,
  "results": []
}
```

### Error

```json
{
  "error": {
    "code": "validation_error",
    "message": "Review the highlighted fields.",
    "field_errors": {
      "items.0.quantity": ["Quantity must be greater than zero."]
    },
    "request_id": "b7b6e2bf-..."
  }
}
```

Common HTTP responses: `400` invalid input, `401` unauthenticated, `403` not permitted, `404` not found or outside accessible scope, `409` state/idempotency conflict, `429` rate limit, `500` unexpected server failure. Error messages must not disclose whether an inaccessible tenant's record exists.

## 3. Resource and operation inventory

All list operations support applicable `q`, `status`, `from`, `to`, `section_id`, and `branch_id` filters, subject to permission and pagination.

| Resource | Endpoints | Notes |
|---|---|---|
| Authentication | `GET /auth/me`, `POST /auth/login`, `POST /auth/logout`, `POST /auth/password-reset` | Login throttled; session/CSRF policy applies. |
| Organization | `GET /organization`, `PATCH /organization`, `GET /business-sections`, `GET /branches` | Admin-only writes; users see assigned scopes only. |
| Currency / FX | `GET /currencies`, `GET/POST /exchange-rates`, `GET /organization/base-currency` | Transaction currencies are LRD/USD; this organization's USD base is fixed before initial posting and locked thereafter. |
| Provider accounts (later) | `GET/POST /provider-accounts`, `PATCH /provider-accounts/{id}` | Deferred; not exposed in MVP. |
| Staff and access | `GET/POST /users`, `PATCH /users/{id}`, `GET/POST /roles`, `PATCH /roles/{id}` | Admin-only; role changes audited. |
| Customers | `GET/POST /customers`, `GET/PATCH /customers/{id}`, `GET /customers/{id}/transactions` | Contact fields restricted by role. |
| Suppliers | `GET/POST /suppliers`, `GET/PATCH /suppliers/{id}`, `GET /suppliers/{id}/transactions` | Includes purchase/payment history. |
| Products | `GET/POST /products`, `GET/PATCH /products/{id}`, `GET /products/{id}/stock-movements` | SKU and section filters. |
| Stock | `GET /stock`, `POST /stock-adjustments`, `GET /stock-adjustments/{id}` | Adjustment requires reason and permission. |
| Sales | `GET /sales`, `POST /sales/preview`, `POST /sales`, `GET /sales/{id}`, `POST /sales/{id}/reverse` | Preview is non-persistent; `POST /sales` revalidates and posts atomically. |
| Receipts | `GET /sales/{id}/receipt?format=pdf` | Authorized, private receipt output. |
| Customer payments | `GET/POST /customer-payments`, `GET /customer-payments/{id}`, `POST /customer-payments/{id}/reverse` | Manual payments and allocations to sale/order balances. |
| Online payments (later) | `POST /payment-intents`, `GET /payment-intents/{id}`, `POST /webhooks/payments/{provider}` | Deferred; MVP records payments received outside the system. |
| Purchases | `GET/POST /purchases`, `GET/PATCH /purchases/{id}`, `POST /purchases/{id}/receipts`, `POST /purchases/{id}/reverse` | PATCH is for drafts only; receiving/reversal is audited and idempotent. |
| Supplier payments | `GET/POST /supplier-payments`, `GET /supplier-payments/{id}` | Allocations to received purchases. |
| Expenses | `GET/POST /expenses`, `GET/PATCH /expenses/{id}`, `POST /expenses/{id}/reverse` | PATCH is for drafts only; posted corrections use audited reversals. |
| Department orders | `GET/POST /orders/photography`, `/orders/printing`, `/orders/clothing`; `GET /orders/{id}`, `POST /orders/{id}/status` | Department-specific validation; common order reference. |
| Dashboard | `GET /dashboard/summary` | Date, section, and branch filters; aggregate access is scoped. |
| Reports | `GET /reports/{name}`, `GET /reports/{name}/export?format=pdf\|xlsx` | Filtered exports; spreadsheet output neutralizes formulas. |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` | In-app MVP. |
| Customer communications (later) | `GET/PATCH /customers/{id}/communication-preferences`, `GET /message-deliveries` | Deferred; MVP supports print/download/manual sharing of receipts, not automated sending. |
| Audit | `GET /audit-events` | Restricted to authorized admin/manager roles. |
| Attachments | `POST /attachments`, `GET /attachments/{id}/download` | Private, size/type limits, authorized access. |

## 4. Example: post a sale

### Request — `POST /api/v1/sales`

```json
{
  "section_id": "7e8617e5-5fbb-4c12-90f2-7f6a73669042",
  "branch_id": "79afcc57-9879-4c85-a1d4-8e6474fab18c",
  "currency": "LRD",
  "customer_id": "f5702a6b-e874-4b2b-9447-7261c4f440f0",
  "items": [
    {
      "product_id": "a5cff13c-5985-45da-8cbf-516f18bc18d3",
      "variant_id": "903f0b4b-5ba9-4268-8ee8-bda8de96cc2e",
      "quantity": "2",
      "unit_price": "25.00",
      "discount_amount": "0.00"
    }
  ],
  "discount_amount": "0.00",
  "payment": {
    "amount": "30.00",
    "method": "cash",
    "reference": null
  },
  "notes": ""
}
```

`POST /sales/preview` accepts the same line and scope fields and returns calculated totals without creating a transaction or reserving stock. The cashier reviews that response, then submits the confirmed sale to `POST /sales`. The post endpoint revalidates stock and prices and commits the sale, payment, stock movements, and audit event atomically. An `Idempotency-Key` header is required for reliable retry after a network timeout. Client-provided amounts are inputs for validation only; the server applies configured pricing and rounding rules and returns canonical totals.

### Response — `201 Created`

```json
{
  "id": "30e31a5d-c4da-4c76-83a8-878cc095e5c4",
  "number": "INV-2026-000123",
  "status": "posted",
  "currency": "LRD",
  "base_currency": "USD",
  "fx_rate_to_base": "0.0053",
  "fx_rate_at": "2026-11-24T08:00:00Z",
  "subtotal": "50.00",
  "discount_total": "0.00",
  "tax_total": "0.00",
  "total": "50.00",
  "base_total": "0.27",
  "paid_amount": "30.00",
  "balance_due": "20.00",
  "created_at": "2026-11-24T08:00:00Z",
  "receipt_url": "/api/v1/sales/30e31a5d-c4da-4c76-83a8-878cc095e5c4/receipt?format=pdf"
}
```

The sample exchange rate and invoice numbering are illustrative only, not a quoted rate or approved default; amount fields `total`, `paid_amount`, and `balance_due` remain in the transaction currency.

## 5. Example: receive purchase goods

### Request — `POST /api/v1/purchases/{purchase_id}/receipts`

```json
{
  "received_at": "2026-11-24T08:00:00Z",
  "reference": "DELIVERY-184",
  "lines": [
    {
      "purchase_line_id": "de5e7ad6-c875-447a-b907-81bb40615b4e",
      "quantity_received": "8"
    }
  ]
}
```

### Response — `201 Created`

```json
{
  "id": "cc5704ce-3906-4c2b-a52f-12e9de874ee4",
  "purchase_id": "0d577351-3c83-4d54-8d74-529ea7f8a5fb",
  "status": "partially_received",
  "stock_movements_created": 1
}
```

The endpoint must reject invalid quantities and duplicate retries; stock updates and receipt records commit atomically.

## 6. Example: create a department order

### Request — `POST /api/v1/orders/clothing`

```json
{
  "section_id": "7e8617e5-5fbb-4c12-90f2-7f6a73669042",
  "branch_id": "79afcc57-9879-4c85-a1d4-8e6474fab18c",
  "customer_id": "f5702a6b-e874-4b2b-9447-7261c4f440f0",
  "due_at": "2026-12-10T17:00:00Z",
  "quantity": "1",
  "product_id": "a5cff13c-5985-45da-8cbf-516f18bc18d3",
  "size": "M",
  "color": "navy",
  "design_notes": "Front crest",
  "custom_name": "A. Example",
  "custom_number": "10",
  "production_cost": "18.00",
  "selling_price": "35.00",
  "deposit": {
    "amount": "10.00",
    "method": "mobile_money",
    "reference": "MANUAL-REF"
  }
}
```

The API validates that the caller can create orders in the selected scope, initializes the configured department status, records the deposit, and returns the outstanding balance. Exact field names and allowed enum values are finalized in OpenAPI.

## 7. Filtering and report parameters

- Dates: `from` and `to` use ISO-8601 dates/timestamps; the server interprets date-only boundaries in the configured organization time zone.
- Currency: transaction entry accepts only `LRD` or `USD`, selected per transaction. The provisional workflow is owner/admin entry of an approved daily rate; clients do not supply arbitrary rates. The server applies the rate according to the accountant-approved effective-time rule and snapshots it on the posted record. Reports may filter or group by transaction currency and show separate subtotals plus the USD-converted consolidated total.
- Scope: `section_id` and `branch_id`; unauthorized IDs return a non-disclosing `404`.
- Payment status: `unpaid`, `partially_paid`, `paid`, and `overdue` where applicable.
- Search: `q` searches only allowlisted fields and accessible records; do not build arbitrary database filters from user input.
- Sorting: `ordering` accepts documented fields only.
- Dashboard summary: `GET /dashboard/summary?from=...&to=...&section_id=...&branch_id=...`.
- Reports use the same financial definitions as the PRD; every response includes source currency (when shown), reporting base currency, selected period, applied scope, and conversion basis.

## 8. Deferred provider and communication contracts (post-MVP)

The following contract shapes are retained for future planning only. Do not implement or include them in MVP acceptance.

### Initiate an online payment

`POST /api/v1/payment-intents` accepts a posted sale/order ID, amount due, currency (`LRD` or `USD`), and method (`mobile_money`, `card`, or supported `bank`). The server validates the outstanding balance and configured provider capability, then creates a pending local intent with an idempotency key and returns the provider's hosted checkout URL or approved next action. Provider-specific tokens/credentials never reach the browser. The payment's currency must match the invoice/order currency unless an explicit cross-currency allocation and FX snapshot are recorded.

Provider callback: `POST /api/v1/webhooks/payments/{provider}`. This endpoint is exempt from browser-session CSRF only because it authenticates the provider's documented signature, timestamp, replay window, and event ID. It stores a minimal event record, acknowledges valid duplicate events safely, and queues idempotent reconciliation. The user's return/redirect page cannot mark a payment as paid.

The payment intent response contains an application intent ID, `pending` state, provider name, checkout URL/next action, amount/currency, and expiration time. Do not return secret keys, signing material, or provider customer credentials.

### Messaging preferences and delivery

Customer preferences are stored per channel. A consent update records channel, state, time, source, and actor where applicable. A committed sale receipt, due reminder, or order update creates an outbox message; the worker checks current consent and template/provider configuration before delivery. `GET /message-deliveries` is permission-scoped and returns channel, provider message reference, state, timestamps, and a safe failure code. API responses and logs must not reveal provider secrets or unnecessary message content.

Message event types initially proposed: receipt, customer payment reminder, and order status/delivery update. Marketing/bulk campaigns are not included. The provider matrix and selected template/sender approval are release prerequisites.

## 9. MVP security, concurrency, and operational requirements

- Check object-level permission and organization/branch scope on every read and write.
- Validate all request bodies with explicit serializers and reject unknown privileged fields.
- Use `transaction.atomic()` and row locks for stock, payments, and receiving.
- Record actor, request ID, timestamp, and action for financial, stock, role, and order-status changes.
- Apply authentication throttling, upload limits, safe errors, and API request size limits.
- Use idempotency keys on sale post, purchase receipt, payment creation, and reversal.
- Provider signature/timestamp verification, callback idempotency, external messaging consent, and sender/template requirements apply only when the deferred integrations are added.
- Do not expose private storage keys; authorize downloads and use short-lived signed URLs if direct object-store delivery is used.
- Return `409 Conflict` for stale state or duplicate/incompatible idempotency operations.
- Generate OpenAPI from the maintained API implementation and validate frontend requests against it in CI.

## 10. Open contract decisions

- Session/login payload and password-reset delivery mechanism.
- Accountant approval of the owner/admin-entered daily FX rate source/effective-time rule, currency precision, tax fields, discounts, receipt numbering, and invoice legal content. USD is the selected reporting base currency.
- Exact list page-size cap and API rate limits.
- Final payment/messaging providers, Liberia merchant eligibility, LRD/USD support, callback security, consent capture, and sender/template approval are deferred-release decisions. MVP order statuses, file limits, export maximum date range, and export execution mode remain to be finalized.
