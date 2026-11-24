from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Customer, Product, ProductVariant
from apps.currencies.models import ExchangeRate
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant
from apps.payments.models import CustomerPayment
from apps.sales.models import Sale


class SalesTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        self.printing = self.org.sections.get(code="printing")
        self.branch = self.org.branches.get()
        self.shirt = Product.objects.create(organization=self.org, section=self.clothing, name="Shirt", selling_price_base=Decimal("12.00"))
        self.shirt_variant = ensure_default_variant(self.shirt)
        apply_movement(
            organization=self.org,
            variant=self.shirt_variant,
            branch=self.branch,
            quantity_delta=Decimal("10"),
            movement_type=StockMovement.Type.OPENING,
            actor=self.owner,
            unit_cost_base=Decimal("5.00"),
        )
        self.design = Product.objects.create(
            organization=self.org,
            section=self.clothing,
            name="Custom print",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("3.00"),
        )
        self.customer = Customer.objects.create(organization=self.org, name="Amara Sesay")
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("190"), effective_date=timezone.localdate(), created_by=self.owner
        )
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.manager = add_member(self.org, "manager", "manager", all_sections=True)

    def body(self, **overrides):
        return {
            "section": str(self.clothing.pk),
            "currency": "USD",
            "items": [{"product": str(self.shirt.pk), "quantity": "2"}],
            **overrides,
        }

    def post(self, user=None, key="k1", **overrides):
        return client_for(user or self.cashier).post("/api/v1/sales/", self.body(**overrides), format="json", HTTP_IDEMPOTENCY_KEY=key)

    def on_hand(self):
        return StockBalance.objects.get(variant=self.shirt_variant).quantity

    def test_cash_sale_reduces_stock_and_records_change(self):
        response = self.post(payment={"amount": "24.00", "method": "cash", "amount_tendered": "30.00"})
        self.assertEqual(response.status_code, 201, response.data)
        sale = response.data
        self.assertEqual((sale["number"], sale["total"], sale["paid_amount"], sale["balance_due"]), ("INV-0001", "24.00", "24.00", "0.00"))
        self.assertEqual(sale["payments"][0]["change"], "6.00")
        self.assertEqual(sale["customer_name"], "Walk-in customer")
        self.assertEqual(self.on_hand(), Decimal("8"))
        movement = StockMovement.objects.get(movement_type="sale")
        self.assertEqual((movement.source_type, movement.source_id), ("sales.sale", sale["id"]))
        self.assertEqual(Sale.objects.get().cost_total_base, Decimal("10.0000"))

    def test_lrd_sale_prices_from_catalog_at_todays_rate(self):
        response = self.post(currency="LRD", customer=str(self.customer.pk))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["lines"][0]["unit_price"], "2280.00")  # 12 USD x 190
        self.assertEqual((response.data["total"], response.data["base_total"]), ("4560.00", "24.00"))

    def test_cashier_cannot_change_price_but_manager_can(self):
        items = [{"product": str(self.shirt.pk), "quantity": "1", "unit_price": "10.00"}]
        refused = self.post(items=items, payment={"amount": "10.00", "method": "cash"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("items.0.unit_price", refused.data["error"]["field_errors"])
        allowed = self.post(user=self.manager, key="k2", items=items, payment={"amount": "10.00", "method": "cash"})
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertTrue(allowed.data["lines"][0]["price_overridden"])

    def test_discounts(self):
        items = [{"product": str(self.shirt.pk), "quantity": "2", "discount": "4.00"}]
        response = self.post(items=items, sale_discount="2.00", payment={"amount": "18.00", "method": "mobile_money", "reference": "MM123"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["subtotal"], response.data["discount_total"], response.data["total"]), ("24.00", "6.00", "18.00"))
        too_much = self.post(key="k2", items=[{"product": str(self.shirt.pk), "quantity": "1", "discount": "13.00"}])
        self.assertIn("items.0.discount", too_much.data["error"]["field_errors"])

    def test_walk_in_must_pay_in_full(self):
        response = self.post(payment={"amount": "10.00", "method": "cash"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("customer", response.data["error"]["field_errors"])

    def test_partial_then_second_payment_and_no_overpayment(self):
        sale = self.post(customer=str(self.customer.pk), payment={"amount": "10.00", "method": "cash"}).data
        self.assertEqual(sale["balance_due"], "14.00")
        url = f"/api/v1/sales/{sale['id']}/payments/"
        client = client_for(self.cashier)
        over = client.post(url, {"amount": "15.00", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY="p1")
        self.assertEqual(over.status_code, 400)
        paid = client.post(
            url, {"amount": "14.00", "method": "bank_transfer", "reference": "TRX-9"}, format="json", HTTP_IDEMPOTENCY_KEY="p2"
        )
        self.assertEqual(paid.status_code, 201, paid.data)
        self.assertEqual((paid.data["balance_due"], len(paid.data["payments"])), ("0.00", 2))
        self.assertEqual(paid.data["lines"][0]["quantity"], "2.000")  # original lines untouched

    def test_insufficient_stock_blocks_and_writes_nothing(self):
        response = self.post(items=[{"product": str(self.shirt.pk), "quantity": "11"}], payment={"amount": "132.00", "method": "cash"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("items.0.quantity", response.data["error"]["field_errors"])
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(self.on_hand(), Decimal("10"))
        ok = self.post(key="k2", payment={"amount": "24.00", "method": "cash"})
        self.assertEqual(ok.data["number"], "INV-0001")  # the failed attempt did not consume a number

    def test_services_do_not_touch_stock(self):
        response = self.post(items=[{"product": str(self.design.pk), "quantity": "3"}], payment={"amount": "9.00", "method": "cash"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(StockMovement.objects.filter(movement_type="sale").count(), 0)

    def test_product_with_options_needs_a_variant(self):
        ProductVariant.objects.create(product=self.shirt, code="L", size="L")
        response = self.post(payment={"amount": "24.00", "method": "cash"})
        self.assertIn("items.0.variant", response.data["error"]["field_errors"])

    def test_retry_with_same_key_posts_once(self):
        first = self.post(payment={"amount": "24.00", "method": "cash"})
        second = self.post(payment={"amount": "24.00", "method": "cash"})
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.on_hand(), Decimal("8"))
        no_key = client_for(self.cashier).post("/api/v1/sales/", self.body(), format="json")
        self.assertEqual(no_key.status_code, 400)

    def test_reversal_returns_stock_at_cost_and_reverses_payments(self):
        sale = self.post(customer=str(self.customer.pk), payment={"amount": "24.00", "method": "cash"}).data
        url = f"/api/v1/sales/{sale['id']}/reverse/"
        self.assertEqual(client_for(self.cashier).post(url, {"reason": "Wrong item"}, format="json").status_code, 403)
        self.assertEqual(client_for(self.manager).post(url, {"reason": ""}, format="json").status_code, 400)
        response = client_for(self.manager).post(url, {"reason": "Customer returned both"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["status"], response.data["balance_due"]), ("reversed", "0.00"))
        balance = StockBalance.objects.get(variant=self.shirt_variant)
        self.assertEqual((balance.quantity, balance.average_cost_base), (Decimal("10.000"), Decimal("5.0000")))
        self.assertEqual(CustomerPayment.objects.get().status, "reversed")
        self.assertEqual(client_for(self.manager).post(url, {"reason": "again"}, format="json").status_code, 409)
        late = client_for(self.cashier).post(
            f"/api/v1/sales/{sale['id']}/payments/", {"amount": "1", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY="late"
        )
        self.assertEqual(late.status_code, 409)

    def test_preview_writes_nothing_and_flags_stock(self):
        response = client_for(self.cashier).post(
            "/api/v1/sales/preview/", self.body(items=[{"product": str(self.shirt.pk), "quantity": "12"}]), format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["total"], response.data["stock_ok"]), ("144.00", False))
        self.assertEqual(response.data["lines"][0]["available_after"], "-2")
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(StockMovement.objects.filter(movement_type="sale").count(), 0)

    def test_costs_visible_only_with_cost_permission(self):
        sale = self.post(payment={"amount": "24.00", "method": "cash"}).data
        self.assertNotIn("cost_total_base", sale)
        self.assertNotIn("unit_cost_base", sale["lines"][0])
        owner_view = client_for(self.owner).get(f"/api/v1/sales/{sale['id']}/").data
        self.assertEqual(owner_view["gross_profit_base"], "14.00")  # 24 - 2 x 5

    def test_section_scope(self):
        self.post(payment={"amount": "24.00", "method": "cash"})
        printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.assertEqual(client_for(printer).get("/api/v1/sales/").status_code, 403)  # no sales.view
        printing_cashier = add_member(self.org, "pcashier", "cashier", sections=["printing"])
        self.assertEqual(client_for(printing_cashier).get("/api/v1/sales/").data["count"], 0)
        refused = self.post(user=printing_cashier, key="k9", payment={"amount": "24.00", "method": "cash"})
        self.assertIn("section", refused.data["error"]["field_errors"])

    def test_unpaid_filter(self):
        self.post(customer=str(self.customer.pk), payment={"amount": "5.00", "method": "cash"})
        self.post(key="k2", payment={"amount": "24.00", "method": "cash"})
        self.assertEqual(client_for(self.owner).get("/api/v1/sales/?unpaid=true").data["count"], 1)
