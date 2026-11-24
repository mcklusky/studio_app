from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Customer, Product, Supplier
from apps.currencies.models import ExchangeRate
from apps.expenses.models import ExpenseCategory
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.services import adjust_stock, ensure_default_variant
from apps.sales.models import Sale

TODAY = timezone.localdate()


class ReportTests(TestCase):
    """Small books whose figures are worked out by hand in each assertion."""

    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.sec = {s.code: s for s in self.org.sections.all()}
        self.branch = self.org.branches.first()
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("200"), effective_date=TODAY, created_by=self.owner
        )
        self.customer = Customer.objects.create(organization=self.org, name="Amara")
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.manager = add_member(self.org, "manager", "manager", all_sections=True)
        self.printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.keys = iter(range(10_000))

        # Clothing: tee costs 4.00, sells 10.00.
        tee = Product.objects.create(
            organization=self.org, section=self.sec["clothing"], name="Tee", selling_price_base=Decimal("10.00"), minimum_stock=Decimal("5")
        )
        self.tee = ensure_default_variant(tee)
        adjust_stock(
            organization=self.org,
            variant=self.tee,
            branch=self.branch,
            quantity_delta=10,
            reason="opening",
            actor=self.owner,
            unit_cost_base=Decimal("4"),
        )
        self.flyer = Product.objects.create(
            organization=self.org,
            section=self.sec["printing"],
            name="Flyer design",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("25.00"),
        )

    def key(self):
        return f"k{next(self.keys)}"

    def post(self, user, url, body, idem=True):
        headers = {"HTTP_IDEMPOTENCY_KEY": self.key()} if idem else {}
        response = client_for(user).post(url, body, format="json", **headers)
        assert response.status_code in (200, 201), response.data
        return response.data

    def sale(self, section, product, qty, currency="USD", paid="0", discount=None):
        body = {
            "section": str(self.sec[section].pk),
            "currency": currency,
            "customer": str(self.customer.pk),
            "items": [{"product": str(getattr(product, "product_id", product.pk)), "quantity": str(qty)}],
            "payment": {"amount": paid, "method": "cash"} if Decimal(paid) > 0 else None,
        }
        if discount:
            body["sale_discount"] = discount
        return self.post(self.owner, "/api/v1/sales/", body)

    def dashboard(self, user=None, **params):
        response = client_for(user or self.owner).get("/api/v1/reports/dashboard/", params)
        assert response.status_code == 200, response.data
        return response.data

    def build_books(self):
        # Clothing USD sale: 3 tees = 30.00, paid 30.00. COGS 12.00.
        self.sale("clothing", self.tee, 3, paid="30.00")
        # Clothing LRD sale: 2 tees = LRD 4,000 (USD 20.00), unpaid. COGS 8.00.
        self.sale("clothing", self.tee, 2, currency="LRD")
        # Printing USD sale: 1 flyer design = 25.00, paid 10.00.
        self.sale("printing", self.flyer, 1, paid="10.00")
        # Printing order: LRD 10,000 (USD 50.00), deposit LRD 4,000 (USD 20.00), delivered, 1 tee used (COGS 4.00).
        order = self.post(
            self.owner,
            "/api/v1/orders/",
            {
                "section": str(self.sec["printing"].pk),
                "customer": str(self.customer.pk),
                "currency": "LRD",
                "total": "10000",
                "due_date": TODAY.isoformat(),
                "detail": {"item": "Banner", "quantity": "1"},
                "deposit": {"amount": "4000", "method": "cash"},
            },
        )
        self.post(self.owner, f"/api/v1/orders/{order['id']}/materials/", {"variant": str(self.tee.pk), "quantity": "1"}, idem=False)
        self.post(self.owner, f"/api/v1/orders/{order['id']}/status/", {"status": "delivered"}, idem=False)
        # Expense: LRD 2,000 (USD 10.00) in clothing.
        rent = ExpenseCategory.objects.create(organization=self.org, name="Rent")
        self.post(
            self.owner,
            "/api/v1/expenses/",
            {
                "category": str(rent.pk),
                "section": str(self.sec["clothing"].pk),
                "expense_date": TODAY.isoformat(),
                "description": "Rent",
                "method": "cash",
                "amount": "2000",
                "currency": "LRD",
            },
        )
        # Purchase: 5 tees at 4.00 = USD 20.00 (not an expense).
        supplier = Supplier.objects.create(organization=self.org, name="Waterside")
        self.post(
            self.owner,
            "/api/v1/purchases/",
            {
                "supplier": str(supplier.pk),
                "section": str(self.sec["clothing"].pk),
                "purchase_date": TODAY.isoformat(),
                "currency": "USD",
                "lines": [{"variant": str(self.tee.pk), "quantity": "5", "unit_cost": "4"}],
            },
            idem=False,
        )
        return order

    def test_combined_figures_reconcile(self):
        self.build_books()
        f = self.dashboard()["figures"]
        self.assertEqual((f["sales"]["base"], f["sales"]["count"]), ("75.00", 3))  # 30 + 20 + 25
        self.assertEqual(f["sales"]["by_currency"], {"LRD": "4000.00", "USD": "55.00"})
        self.assertEqual(f["orders_delivered"]["base"], "50.00")
        self.assertEqual(f["revenue_base"], "125.00")
        self.assertEqual(f["cash_collected"]["base"], "60.00")  # 30 + 10 + 20 (deposit)
        self.assertEqual(f["cash_collected"]["by_currency"], {"LRD": "4000.00", "USD": "40.00"})
        self.assertEqual(f["cost_of_goods_sold_base"], "24.00")  # 12 + 8 + 4
        self.assertEqual(f["gross_profit_base"], "101.00")  # 125 − 24
        self.assertEqual(f["expenses"]["base"], "10.00")
        self.assertEqual(f["net_profit_base"], "91.00")
        self.assertEqual(f["purchases"]["base"], "20.00")

    def test_sections_add_up_to_combined_without_duplicates(self):
        self.build_books()
        combined = self.dashboard()["figures"]
        parts = [self.dashboard(section=str(self.sec[c].pk))["figures"] for c in ("clothing", "printing", "photography")]
        for key in ("revenue_base", "gross_profit_base", "net_profit_base"):
            self.assertEqual(sum(Decimal(p[key]) for p in parts), Decimal(combined[key]), key)
        self.assertEqual(sum(Decimal(p["cash_collected"]["base"]) for p in parts), Decimal(combined["cash_collected"]["base"]))
        printing = parts[1]
        self.assertEqual((printing["revenue_base"], printing["cash_collected"]["base"]), ("75.00", "30.00"))

    def test_balances_stock_and_orders(self):
        self.build_books()
        data = self.dashboard()
        # Owed: LRD sale 4,000 (USD 20) + printing sale 15.00. The delivered order owes LRD 6,000 (USD 30).
        self.assertEqual(data["receivables"]["by_currency"], {"LRD": "10000.00", "USD": "15.00"})
        self.assertEqual(data["receivables"]["base"], "65.00")
        self.assertEqual(data["payables"]["base"], "20.00")
        # 10 − 3 − 2 − 1 = 4 tees left (purchase not yet received), at 4.00; minimum is 5 so it is low.
        self.assertEqual(data["stock"], {"low_count": 1, "out_count": 0, "value_base": "16.00", "basis": "moving weighted-average cost"})
        self.assertEqual(data["orders"]["active"], 0)

    def test_reversals_drop_out(self):
        sale = self.sale("clothing", self.tee, 1, paid="10.00")
        client_for(self.manager).post(f"/api/v1/sales/{sale['id']}/reverse/", {"reason": "Returned"}, format="json")
        f = self.dashboard()["figures"]
        self.assertEqual((f["sales"]["base"], f["cash_collected"]["base"], f["cost_of_goods_sold_base"]), ("0.00", "0.00", "0.00"))
        self.assertEqual(Sale.objects.get(pk=sale["id"]).status, "reversed")

    def test_period_filter_and_previous_period(self):
        old = self.sale("clothing", self.tee, 1)
        Sale.objects.filter(pk=old["id"]).update(posted_at=timezone.now() - timedelta(days=1))
        self.sale("clothing", self.tee, 2)
        today = self.dashboard()
        self.assertEqual(today["figures"]["sales"]["base"], "20.00")
        self.assertEqual(today["previous"]["revenue_base"], "10.00")
        both = self.dashboard(**{"from": (TODAY - timedelta(days=1)).isoformat(), "to": TODAY.isoformat()})
        self.assertEqual(both["figures"]["sales"]["base"], "30.00")
        self.assertEqual(len(both["series"]), 2)
        bad = client_for(self.owner).get(
            "/api/v1/reports/dashboard/", {"from": TODAY.isoformat(), "to": (TODAY - timedelta(days=3)).isoformat()}
        )
        self.assertEqual(bad.status_code, 400)

    def test_role_visibility(self):
        self.build_books()
        cashier = self.dashboard(self.cashier)
        self.assertIn("sales", cashier["figures"])
        for hidden in ("expenses", "purchases", "gross_profit_base", "net_profit_base", "cost_of_goods_sold_base"):
            self.assertNotIn(hidden, cashier["figures"])
        self.assertNotIn("payables", cashier)
        self.assertNotIn("expenses_base", cashier["by_section"][0])
        self.assertEqual(client_for(self.cashier).get("/api/v1/reports/summary/").status_code, 403)

        printer = self.dashboard(self.printer)
        self.assertEqual(printer["figures"], {})
        self.assertNotIn("receivables", printer)
        self.assertNotIn("value_base", printer["stock"])
        self.assertTrue(all(item["kind"] == "order" for item in printer["recent"]))
        foreign = client_for(self.printer).get("/api/v1/reports/dashboard/", {"section": str(self.sec["clothing"].pk)})
        self.assertEqual(foreign.status_code, 400)

    def test_best_products_spread_sale_discount(self):
        # 2 tees (20.00) + nothing else, 5.00 sale discount → tee revenue 15.00.
        self.sale("clothing", self.tee, 2, discount="5.00")
        rows = client_for(self.owner).get("/api/v1/reports/products/").data["rows"]
        self.assertEqual(
            (rows[0]["label"], rows[0]["quantity"], rows[0]["revenue_base"], rows[0]["profit_base"]), ("Tee", "2", "15.00", "7.00")
        )
        manager_rows = client_for(self.manager).get("/api/v1/reports/customers/").data["rows"]
        self.assertEqual(manager_rows[0], {"id": str(self.customer.pk), "name": "Amara", "revenue_base": "15.00", "transactions": 1})

    def test_summary_and_debts(self):
        self.build_books()
        summary = client_for(self.owner).get("/api/v1/reports/summary/").data
        self.assertEqual(
            summary["expenses_by_category"], [{"id": summary["expenses_by_category"][0]["id"], "name": "Rent", "base": "10.00"}]
        )
        self.assertIn("net_profit", summary["definitions"])
        debts = client_for(self.owner).get("/api/v1/reports/debts/").data
        self.assertEqual(debts["receivables"]["top"][0]["name"], "Amara")
        stock = client_for(self.owner).get("/api/v1/reports/stock/").data
        self.assertEqual(stock["rows"], [{"section": "Clothing", "category": "Uncategorised", "quantity": "4", "value_base": "16.00"}])
