# Admin guide: running Just Smile Empire day to day

For the owner and managers. No technical knowledge needed.

## Every morning
1. **Enter today's LRD rate.** The bell shows "Enter today's LRD rate" until you do. LRD sales, orders and expenses use the rate for their date, and a rate cannot be changed once used. If you make a mistake, enter a corrected rate.
2. **Open the bell.** It lists overdue orders, orders due today or tomorrow, photo shoots coming up, items out of stock or running low, customers who have owed for more than 14 days, and suppliers unpaid after 30 days. Click an alert to open the record. Alerts disappear by themselves when the problem is fixed.

## Staff and access (Team & access)
* **Add someone:** enter their name, choose a role and the sections they work in. The app creates a temporary password. Give it to them in person; they change it by clicking their name at the bottom of the menu.
* **Roles:** *Owner admin* can do everything. *Manager* runs the business but cannot manage staff. *Cashier* handles sales and payments. *Department staff* work their department's orders. The **Roles** tab shows exactly what each role can do. Create a custom role if you need a different mix.
* **When someone leaves:** click **Deactivate** that day. They are signed out at once. Everything they recorded stays under their name.
* **Forgotten password:** **Reset password** gives a new temporary password and signs them out everywhere.
* **Activity log:** a permanent record of who did what, such as sales, reversals, price changes and sign-ins. Nobody can edit or delete it.

## Money rules to know
* **Two currencies, one report currency.** Each sale, payment, order or expense is in LRD or USD and keeps its own amount. Reports convert to USD using the rate saved on each transaction. LRD and USD subtotals are always shown separately.
* **Mistakes are reversed, never deleted.** A wrong sale, payment, expense or goods receipt is *reversed* with a reason. The original and the reversal both stay in the records.
* **Payments can't exceed what is owed.** Paying more than the balance is refused; there is no customer credit yet.
* **Orders:** a deposit counts as cash collected when received; the order counts as revenue when it is **delivered**. Cancelling an order with a deposit needs the deposit refunded and reversed first.
* **Stock cost** is the weighted average of what you paid, including shipping spread over the items. Profit uses that cost.

## Opening products and stock
To load your product list and the stock you have on day one, fill in a copy of [`catalog-template.csv`](./catalog-template.csv) in Excel or Google Sheets, then save it as CSV:

| Column | What to put |
|---|---|
| section | Clothing, Printing or Photography |
| name | Product or service name. Repeat the name on several rows for different sizes/colours |
| kind | `product` or `service` (services have no stock) |
| category, sku | Optional |
| size, color | Optional, one row per size/colour |
| selling_price, buying_price | In USD |
| minimum_stock | When to show "running low" |
| opening_quantity, opening_unit_cost | What you have now and what each cost you (USD) |

Give the file to whoever runs the server. They check it first, which changes nothing, and then import it:
```
python manage.py import_catalog --file products.csv --user <owner username> --dry-run
python manage.py import_catalog --file products.csv --user <owner username>
```
If any row has a problem, **nothing** is imported and every problem is listed with its line number. After importing, count a few items on the shelf and compare them with **Inventory**.

## Month end
1. **Reports → This month → Profit & loss → ⇣ Excel** (or PDF) for your accountant.
2. **Debts** tab: who owes you and whom you owe.
3. **Stock value** tab: value of stock on hand. Do a physical count of a few items and correct differences in **Inventory → Adjust** with the reason "Stock count correction".
4. Ask whoever runs the server to confirm that last month's backup restore drill was done.

## Getting help
When something fails, the message shows **Reference: xxxxxxxx**. Send that reference with a description to whoever runs the server; it finds the exact error in the logs.
