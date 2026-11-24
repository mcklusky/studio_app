# Roadmap: deferred work

These items are deliberately **not** in the first release. Each one needs the design work listed under it, and an approved plan, before development starts. Plan task numbers are in brackets.

## Offline transaction entry (REQ-036, T088)

**Today:** the app needs a connection. Each sale, payment and stock movement is checked and committed by the server at once. If the connection drops, the screen shows an error and nothing is saved halfway. Idempotency keys make a retry after a dropped connection safe: a sale is never recorded twice.

**Why it is deferred:** offline entry breaks the guarantees the books rely on.
- **Stock:** two tills selling the last shirt while offline would both succeed. The server can't refuse the second sale after the fact without un-selling something a customer has already left with.
- **Numbers:** receipt numbers (INV-…) are issued by the server in strict sequence. Offline receipts need provisional numbers and a mapping to the final ones that customers can follow.
- **Prices and rates:** an offline device could use an out-of-date catalog price or LRD rate.
- **Security:** an offline device holds business data and pending transactions, so it needs encrypted local storage and a plan for lost or stolen phones. Staff who are deactivated while a device is offline must not be able to sync work afterwards.

**Design needed before building:**
1. **Conflicts:** what happens when the server cannot accept an offline transaction (stock gone, price changed, staff deactivated, period closed). Who resolves it, on which screen, and what the customer's receipt says.
2. **Reconciliation:** a sync queue with per-device sequence numbers, server-side re-validation of every queued transaction, an audit trail for "entered offline at X, synced at Y", and a report of unsynced or rejected items.
3. **Scope:** probably sales and payments only, with stock refusal relaxed to a manager-approved negative-stock exception. No offline orders, purchases or adjustments.
4. **Security:** encrypted IndexedDB storage, a device registration and revocation list, and a maximum offline period.
5. **Accountant sign-off** on provisional numbering and negative-stock corrections.

## Other deferred items

| Item | Plan | Depends on |
|---|---|---|
| Mobile-money / card payments through a provider (payment intents, signed callbacks, settlement reconciliation) | T056–T059 | Provider selection and contract ([provider research](../provider-research.md)) |
| SMS / WhatsApp customer messages (consent, outbox, delivery status) | T080–T082 | Provider selection, consent wording |
| Public customer website (services and prices, booking requests, order tracking) | T089–T095 (Phase 11) | Go-live of the staff app. Online deposits need T056 |
| Manager override to sell more than recorded stock | Owner sign-off rule 11 | Owner decision |
| Install as a phone app (PWA: icon, full-screen) without offline writes | — | None; small |
| Exchange gains/losses on late LRD payments | Owner sign-off rule 4 | Accountant decision |
| Sales tax / GST lines on receipts and reports | Owner sign-off rule 7 | Accountant decision |
