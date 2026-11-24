# Owner and accountant sign-off (T087)

The app follows the rules below today. Several were chosen provisionally during the build. Before the figures are treated as the official books, the owner (and the business's accountant where marked 🧾) should confirm each rule or ask for a change. Most changes are small.

Tick **Agree**, or write the change wanted.

## Money and currency

| # | Rule as built | Agree / change |
|---|---|---|
| 1 🧾 | USD is the reporting currency. Each transaction is in LRD or USD and keeps its own amount. | |
| 2 🧾 | The LRD rate is entered daily by an owner/admin as "LRD per 1 USD". A transaction uses the latest rate on or before its date, and that rate is saved with it permanently. | |
| 3 🧾 | Conversion: USD = LRD ÷ rate, rounded half-up to the cent. Reports never re-convert old transactions at today's rate. | |
| 4 🧾 | No exchange gain or loss is calculated. An LRD invoice paid later in LRD is simply settled; its USD value stays as on the invoice date. | |
| 5 | Payments settle only invoices in the same currency. LRD cash cannot pay a USD invoice yet. | |
| 6 | A payment can never be more than what is owed. There is no customer credit or overpayment balance. | |
| 7 🧾 | **No sales tax / GST is applied** and receipts show no tax line. Confirm none is required, or give the rate and receipt wording. | |

## Sales, receipts and payments

| # | Rule as built | Agree / change |
|---|---|---|
| 8 | Receipt numbers INV-0001…, payments PAY-…, orders ORD-…, purchases PO-…, expenses EXP-…. Numbers never reset. | |
| 9 | Selling at a different price than the catalog needs a manager (permission "sell at a price other than the catalog price"). | |
| 10 | A sale that leaves money owing must have a named customer (no walk-in debts). | |
| 11 | Selling more than is in stock is refused. (A manager override is not built yet; say if you need it.) | |
| 12 🧾 | Mistakes are corrected by **reversal with a reason**, never by editing or deleting. Reversing a sale puts its stock back and refunds only that sale's share of any payment. | |
| 13 | Receipt shows business name, receipt number, date/time, staff, customer, items, discounts, total, paid, balance and change. Add anything required (address, phone, tax ID, footer text)? | |

## Stock and costs

| # | Rule as built | Agree / change |
|---|---|---|
| 14 🧾 | Stock is valued at **moving weighted-average cost** in USD. | |
| 15 🧾 | Shipping and other purchase costs are spread over the purchase lines **by value** and become part of item cost. | |
| 16 🧾 | Purchases are not an expense when bought. Their cost reaches profit as **cost of goods sold** when the items are sold or used on an order. | |
| 17 | Stock only increases when goods are **received**, not when the purchase is created. | |
| 18 | Opening stock is entered at its unit cost (import or Inventory → Adjust). | |

## Department orders

| # | Rule as built | Agree / change |
|---|---|---|
| 19 🧾 | A deposit is **cash collected** when received. The order counts as **revenue on the day it is delivered**, at its agreed price. | |
| 20 | An order can be marked delivered while money is still owed (with a warning). Or should full payment be required first? | |
| 21 🧾 | Cancelling an order that has a deposit is blocked until the deposit is refunded and reversed. Are deposits sometimes kept (non-refundable)? If so, how should a kept deposit be recorded? | |
| 22 | Orders only take stock when materials are recorded on them (e.g. blank shirts). The cost of those materials counts in profit when the order is delivered. | |
| 23 | Production cost entered on an order is information only. Outside costs actually paid should be recorded as expenses. | |

## Reports

| # | Rule as built | Agree / change |
|---|---|---|
| 24 🧾 | Gross profit = sales + orders delivered − cost of goods sold. Net profit = gross profit − expenses. | |
| 25 | Sales and cash collected are shown separately and never mixed. | |
| 26 | A payment reversed later is removed from its original day's cash (not shown as a negative on the reversal day). | |
| 27 | Customer and supplier balances and stock value are "as of now", whatever period is chosen. | |

## Access and alerts

| # | Rule as built | Agree / change |
|---|---|---|
| 28 | Role permissions as shown in **Team & access → Roles**. Cashiers cannot see costs, profit, expenses or suppliers. Department staff see only their section's orders and stock. | |
| 29 | Alerts: customer owing over **14 days**, supplier unpaid over **30 days**, orders due **today/tomorrow**, shoots within **2 days**. | |
| 30 | Records are kept indefinitely. Backups are kept 30 days on the server, plus an off-site copy (runbook §4). | |

---

Signed (owner): ____________________  Date: ___________

Reviewed (accountant): ____________________  Date: ___________
