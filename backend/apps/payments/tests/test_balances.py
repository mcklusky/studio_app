from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Customer, Product, Supplier
from apps.currencies.models import ExchangeRate
from apps.expenses.models import ExpenseCategory
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.services import ensure_default_variant
from apps.payments.models import CustomerPayment, SupplierPayment
from apps.purchasing.models import Purchase
from apps.sales.models import Sale

TODAY = timezone.localdate()


class Base(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        self.service = Product.objects.create(
            organization=self.org,
            section=self.clothing,
            name="Design fee",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("10.00"),
        )
        self.customer = Customer.objects.create(organization=self.org, name="Amara")
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("200"), effective_date=TODAY, created_by=self.owner
        )
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.manager = add_member(self.org, "manager", "manager", all_sections=True)
        self.keys = iter(range(10_000))

    def key(self):
        return f"k{next(self.keys)}"

    def sale(self, qty, paid, currency="USD"):
        body = {
            "section": str(self.clothing.pk),
            "currency": currency,
            "customer": str(self.customer.pk),
            "items": [{"product": str(self.service.pk), "quantity": str(qty)}],
            "payment": {"amount": paid, "method": "cash"} if Decimal(paid) > 0 else None,
        }
        response = client_for(self.cashier).post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY=self.key())
        assert response.status_code == 201, response.data
        return response.data

    def receive(self, amount, user=None, currency="USD", **extra):
        body = {"customer": str(self.customer.pk), "currency": currency, "amount": amount, "method": "mobile_money", **extra}
        return client_for(user or self.cashier).post("/api/v1/customer-payments/", body, format="json", HTTP_IDEMPOTENCY_KEY=self.key())


class CustomerBalanceTests(Base):
    def test_balances_per_currency_and_filter(self):
        self.sale(3, "10.00")  # USD 20 due
        self.sale(1, "0", currency="LRD")  # LRD 2,000 due
        Customer.objects.create(organization=self.org, name="Paid up")
        rows = client_for(self.owner).get("/api/v1/customers/?has_balance=true").data["results"]
        self.assertEqual([(r["name"], r["balances"]) for r in rows], [("Amara", {"USD": "20.00", "LRD": "2000.00"})])

    def test_payment_allocates_oldest_first(self):
        first, second = self.sale(2, "5.00"), self.sale(2, "0")  # 15 due, then 20 due
        response = self.receive("25.00")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            [(a["number"], a["amount"]) for a in response.data["allocations"]], [(first["number"], "15.00"), (second["number"], "10.00")]
        )
        self.assertEqual(Sale.objects.get(pk=second["id"]).paid_amount, Decimal("10.00"))

    def test_explicit_allocation_and_validation(self):
        first, second = self.sale(2, "0"), self.sale(2, "0")
        ok = self.receive("5.00", allocations={second["id"]: "5.00"})
        self.assertEqual(ok.data["allocations"][0]["number"], second["number"])
        mismatch = self.receive("5.00", allocations={first["id"]: "3.00"})
        self.assertIn("allocations", mismatch.data["error"]["field_errors"])
        too_much = self.receive("100.00")
        self.assertIn("amount", too_much.data["error"]["field_errors"])
        wrong_currency = self.receive("5.00", currency="LRD")
        self.assertEqual(wrong_currency.status_code, 400)

    def test_reversing_a_payment_reopens_balance(self):
        sale = self.sale(2, "0")
        payment = self.receive("20.00").data
        url = f"/api/v1/customer-payments/{payment['id']}/reverse/"
        self.assertEqual(client_for(self.cashier).post(url, {"reason": "Bounced"}, format="json").status_code, 403)
        self.assertEqual(client_for(self.manager).post(url, {"reason": "Mobile money transfer bounced"}, format="json").status_code, 200)
        self.assertEqual(Sale.objects.get(pk=sale["id"]).paid_amount, Decimal("0.00"))
        self.assertEqual(client_for(self.manager).post(url, {"reason": "again"}, format="json").status_code, 409)

    def test_sale_reversal_refunds_only_its_share(self):
        first, second = self.sale(1, "0"), self.sale(1, "0")  # 10 + 10 due
        payment = self.receive("20.00").data  # covers both
        client_for(self.manager).post(f"/api/v1/sales/{first['id']}/reverse/", {"reason": "Cancelled job"}, format="json")
        self.assertEqual(CustomerPayment.objects.get(pk=payment["id"]).status, "reversed")
        replacement = CustomerPayment.objects.get(status="posted", allocations__sale_id=second["id"])
        self.assertEqual(replacement.amount, Decimal("10.00"))
        self.assertEqual(Sale.objects.get(pk=second["id"]).paid_amount, Decimal("10.00"))  # still fully paid

    def test_statement_and_visibility(self):
        self.sale(2, "5.00")
        statement = client_for(self.owner).get(f"/api/v1/customers/{self.customer.pk}/statement/").data
        self.assertEqual(statement["balances"], {"USD": "15.00"})
        self.assertEqual(statement["open_documents"][0]["due"], "15.00")
        self.assertEqual(len(statement["payments"]), 1)
        printer = add_member(self.org, "printer", "department-staff", all_sections=True)
        rows = client_for(printer).get("/api/v1/customers/").data["results"]
        self.assertNotIn("balances", rows[0])
        self.assertEqual(client_for(printer).get(f"/api/v1/customers/{self.customer.pk}/statement/").status_code, 403)


class SupplierBalanceTests(Base):
    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(organization=self.org, name="Waterside")
        self.shirt = ensure_default_variant(Product.objects.create(organization=self.org, section=self.clothing, name="Shirt"))

    def purchase(self, total_units, currency="USD"):
        body = {
            "supplier": str(self.supplier.pk),
            "section": str(self.clothing.pk),
            "purchase_date": TODAY.isoformat(),
            "currency": currency,
            "lines": [{"variant": str(self.shirt.pk), "quantity": str(total_units), "unit_cost": "10"}],
        }
        response = client_for(self.owner).post("/api/v1/purchases/", body, format="json")
        assert response.status_code == 201, response.data
        return response.data

    def pay(self, amount, user=None, **extra):
        body = {"supplier": str(self.supplier.pk), "currency": "USD", "amount": amount, "method": "bank_transfer", **extra}
        return client_for(user or self.manager).post("/api/v1/supplier-payments/", body, format="json", HTTP_IDEMPOTENCY_KEY=self.key())

    def test_pay_supplier_oldest_first_and_balance(self):
        _, second = self.purchase(5), self.purchase(5)  # 50 + 50
        response = self.pay("70.00", reference="TRX-1")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([a["amount"] for a in response.data["allocations"]], ["50.00", "20.00"])
        rows = client_for(self.owner).get("/api/v1/suppliers/").data["results"]
        self.assertEqual(rows[0]["balances"], {"USD": "30.00"})
        detail = client_for(self.owner).get(f"/api/v1/purchases/{second['id']}/").data
        self.assertEqual(detail["paid_amount"], "20.00")

    def test_cashier_cannot_pay_suppliers(self):
        self.purchase(1)
        self.assertEqual(self.pay("5.00", user=self.cashier).status_code, 403)

    def test_cannot_overpay_or_cancel_paid_purchase(self):
        purchase = self.purchase(1)
        self.assertEqual(self.pay("11.00").status_code, 400)
        payment = self.pay("10.00").data
        cancel = client_for(self.owner).post(f"/api/v1/purchases/{purchase['id']}/cancel/", {"reason": "Dup"}, format="json")
        self.assertEqual(cancel.status_code, 409)
        client_for(self.manager).post(f"/api/v1/supplier-payments/{payment['id']}/reverse/", {"reason": "Wrong supplier"}, format="json")
        self.assertEqual(Purchase.objects.get(pk=purchase["id"]).paid_amount, Decimal("0.00"))
        self.assertEqual(SupplierPayment.objects.get().status, "reversed")
        cancel = client_for(self.owner).post(f"/api/v1/purchases/{purchase['id']}/cancel/", {"reason": "Dup"}, format="json")
        self.assertEqual(cancel.status_code, 200)

    def test_edit_cannot_drop_total_below_paid(self):
        purchase = self.purchase(5)
        self.pay("40.00")
        line = {"variant": str(self.shirt.pk), "quantity": "3", "unit_cost": "10"}
        response = client_for(self.owner).patch(f"/api/v1/purchases/{purchase['id']}/", {"lines": [line]}, format="json")
        self.assertEqual(response.status_code, 400)


class ExpenseTests(Base):
    def setUp(self):
        super().setUp()
        self.rent = ExpenseCategory.objects.create(organization=self.org, name="Rent")

    def record(self, user=None, key=True, **overrides):
        body = {
            "category": str(self.rent.pk),
            "section": str(self.clothing.pk),
            "expense_date": TODAY.isoformat(),
            "description": "Shop rent",
            "method": "cash",
            "amount": "20000",
            "currency": "LRD",
            **overrides,
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": self.key()} if key else {}
        return client_for(user or self.owner).post("/api/v1/expenses/", body, format="json", **headers)

    def test_lrd_expense_snapshots_rate(self):
        response = self.record()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["number"], response.data["base_amount"], response.data["status"]), ("EXP-0001", "100.00", "posted"))

    def test_validation(self):
        self.assertEqual(self.record(key=False).status_code, 400)
        future = self.record(expense_date=(TODAY + timezone.timedelta(days=2)).isoformat())
        self.assertIn("expense_date", future.data["error"]["field_errors"])
        self.assertEqual(self.record(amount="0").status_code, 400)
        self.assertEqual(self.record(user=self.cashier).status_code, 403)

    def test_reverse_and_totals(self):
        kept = self.record().data
        voided = self.record(amount="5", currency="USD").data
        url = f"/api/v1/expenses/{voided['id']}/reverse/"
        self.assertEqual(client_for(self.owner).post(url, {"reason": ""}, format="json").status_code, 400)
        self.assertEqual(client_for(self.owner).post(url, {"reason": "Entered twice"}, format="json").data["status"], "reversed")
        totals = client_for(self.owner).get("/api/v1/expenses/").data["totals"]
        self.assertEqual(totals, {"by_currency": {"LRD": "20000.00"}, "base_total": "100.00"})
        self.assertEqual(kept["status"], "posted")
