# Sample discovery decisions

These are working defaults to unblock the first build, not stakeholder approvals. Replace or confirm them during discovery before production use.

| Topic | Sample decision | Status / change point |
|---|---|---|
| Country and location | Liberia; one location with Clothing, Printing, and Photography sections | Planning assumption; configurable organization/branch records |
| Time zone | `Africa/Monrovia`; store timestamps in UTC and display local time | Sample; confirm with owner |
| Currency | Accept LRD and USD per transaction; report in USD; retain original amount and FX snapshot | Selected product direction; confirm accountant policy |
| FX rate | Owner/admin enters one daily LRD-per-USD rate, effective from local midnight; never rewrite posted transaction snapshots | Sample workflow; confirm source, approval, and effective-time rule |
| Tax | No tax calculation in initial sample; store configurable tax settings before enabling tax invoices | Provisional; owner/accountant must confirm legal treatment |
| Inventory costing | Moving weighted-average cost, calculated on confirmed receipts | Selected product direction; confirm landed costs, discounts, and returns |
| Discounts and refunds | Record discount on the sale; reverse posted sales with linked, reasoned reversal records; no editing posted history | Sample control; accountant to confirm calculations and authorization |
| Deposits | Treat customer deposits as liabilities until applied to a completed order | Provisional accounting treatment; accountant approval required |
| Staff | Sample roles: Owner/Admin, Manager, Cashier, Department Staff; apply least privilege and section scope | Starter role set; map to actual staff and duties |
| Data volumes | Plan for 10 named users and up to 100 transactions/day initially | Capacity placeholder; measure and revise |
| Opening data | Manually enter opening catalog, stock quantities, cost basis, users, and expense categories; no legacy transaction import | Sample cutover approach; owner to approve opening balances |
| Payments | Start with manual cash/bank/mobile-money recording; add live provider checkout only after Liberia merchant and currency eligibility is confirmed | Provider-neutral starting point |
| Messaging | No live messages until consent is recorded and sender/provider setup is approved; keep message delivery behind adapters | Provider-neutral starting point |

## Provider comparison record

No provider has been approved. Keep this matrix current during onboarding; public availability alone does not establish merchant eligibility or settlement support.

| Channel | Sample selection | Liberia merchant eligibility | LRD/USD | Sandbox and callbacks | Fees / sender requirements |
|---|---|---|---|---|---|
| Mobile money | Undecided; manual recording in first build | Verify with provider | Verify | Verify signed callbacks and replay controls | Obtain written merchant pricing |
| Card / bank | Undecided; manual recording in first build | Verify with provider/acquirer | Verify | Verify sandbox and settlement reports | Obtain processing and payout fees |
| Email | Adapter interface only | Verify account/sender requirements | N/A | Verify delivery events | Verify sender/domain setup |
| SMS | Adapter interface only | Verify sender ID and route | N/A | Verify delivery reports | Obtain per-message pricing |
| WhatsApp | Adapter interface only | Verify business onboarding, templates, and opt-in | N/A | Verify webhook events | Obtain conversation/template fees |
