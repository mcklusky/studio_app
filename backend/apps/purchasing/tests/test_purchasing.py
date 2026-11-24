from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Product, Supplier
from apps.currencies.models import ExchangeRate
from apps.currencies.services import snapshot_for
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant
from apps.purchasing.models import Purchase

TODAY = timezone.localdate()


def rate(org, user, units, on=TODAY, currency="LRD"):
    return ExchangeRate.objects.create(
        organization=org, currency=currency, units_per_usd=Decimal(units), effective_date=on, created_by=user
    )


class ExchangeRateTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def test_usd_needs_no_rate(self):
        snap = snapshot_for(self.org, "USD", TODAY)
        self.assertEqual((snap.units_per_usd, snap.to_base("12.34")), (Decimal("1"), Decimal("12.34")))

    def test_uses_latest_rate_on_or_before_date(self):
        rate(self.org, self.owner, "180", TODAY - timedelta(days=5))
        rate(self.org, self.owner, "190", TODAY)
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY - timedelta(days=1)).units_per_usd, Decimal("180"))
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY).to_base("19000"), Decimal("100.00"))

    def test_later_entry_same_day_supersedes(self):
        rate(self.org, self.owner, "190")
        rate(self.org, self.owner, "200")
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY).units_per_usd, Decimal("200"))

    def test_missing_rate_is_a_validation_error(self):
        with self.assertRaises(ValidationError):
            snapshot_for(self.org, "LRD", TODAY)

    def test_rates_are_append_only(self):
        entry = rate(self.org, self.owner, "190")
        entry.units_per_usd = Decimal("1")
        with self.assertRaises(ValueError):
            entry.save()

    def test_api_permissions(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        body = {"units_per_usd": "191.5", "effective_date": TODAY.isoformat()}
        self.assertEqual(client_for(cashier).post("/api/v1/exchange-rates/", body, format="json").status_code, 403)
        self.assertEqual(client_for(self.owner).post("/api/v1/exchange-rates/", body, format="json").status_code, 201)
        current = client_for(cashier).get("/api/v1/exchange-rates/current/").data
        self.assertEqual(current["rates"]["LRD"]["units_per_usd"], "191.500000")
        self.assertTrue(current["rates"]["LRD"]["is_today"])


class PurchasingTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        self.supplier = Supplier.objects.create(organization=self.org, name="Waterside Wholesale")
        self.shirt = ensure_default_variant(Product.objects.create(organization=self.org, section=self.clothing, name="Shirt"))
        self.cap = ensure_default_variant(Product.objects.create(organization=self.org, section=self.clothing, name="Cap"))
        self.client = client_for(self.owner)
        rate(self.org, self.owner, "200")

    def create(self, **overrides):
        body = {
            "supplier": str(self.supplier.pk),
            "section": str(self.clothing.pk),
            "purchase_date": TODAY.isoformat(),
            "currency": "LRD",
            "shipping_cost": "1000",
            "supplier_reference": "INV-77",
            "lines": [
                {"variant": str(self.shirt.pk), "quantity": "10", "unit_cost": "600"},  # 6,000
                {"variant": str(self.cap.pk), "quantity": "5", "unit_cost": "800"},  # 4,000
            ],
            **overrides,
        }
        return self.client.post("/api/v1/purchases/", body, format="json")

    def receive(self, purchase, lines, key="r1", client=None):
        return (client or self.client).post(
            f"/api/v1/purchases/{purchase['id']}/receive/", {"lines": lines}, format="json", HTTP_IDEMPOTENCY_KEY=key
        )

    def line_id(self, purchase, variant):
        return next(line["id"] for line in purchase["lines"] if line["variant"] == str(variant.pk))

    def on_hand(self, variant):
        balance = StockBalance.objects.filter(variant=variant).first()
        return balance.quantity if balance else Decimal("0")

    def test_create_snapshots_fx_and_totals(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["number"], "PO-0001")
        self.assertEqual((data["subtotal"], data["total"], data["base_total"]), ("10000.00", "11000.00", "55.00"))
        self.assertEqual(data["fx_units_per_usd"], "200.000000")
        self.assertEqual(self.create().data["number"], "PO-0002")

    def test_creating_purchase_does_not_change_stock(self):
        self.create()
        self.assertFalse(StockMovement.objects.exists())

    def test_partial_receipt_adds_stock_at_landed_cost(self):
        purchase = self.create().data
        response = self.receive(purchase, {self.line_id(purchase, self.shirt): "4"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "partially_received")
        self.assertEqual(self.on_hand(self.shirt), Decimal("4"))
        # Shipping 1,000 split by value: shirt share 600 over 10 units -> 660 LRD/unit -> 3.30 USD.
        movement = StockMovement.objects.get(variant=self.shirt)
        self.assertEqual(movement.unit_cost_base, Decimal("3.3000"))
        self.assertEqual(movement.source_type, "purchasing.goodsreceipt")

    def test_full_receipt_marks_received(self):
        purchase = self.create().data
        lines = {self.line_id(purchase, self.shirt): "10", self.line_id(purchase, self.cap): "5"}
        self.assertEqual(self.receive(purchase, lines).data["status"], "received")
        self.assertEqual(self.receive(purchase, lines, key="again-2").status_code, 409)

    def test_cannot_receive_more_than_ordered(self):
        purchase = self.create().data
        response = self.receive(purchase, {self.line_id(purchase, self.shirt): "11"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StockMovement.objects.exists())

    def test_duplicate_receive_request_is_applied_once(self):
        purchase = self.create().data
        lines = {self.line_id(purchase, self.shirt): "3"}
        self.receive(purchase, lines, key="same")
        replay = self.receive(purchase, lines, key="same")
        self.assertEqual(replay["Idempotent-Replayed"], "true")
        self.assertEqual(self.on_hand(self.shirt), Decimal("3"))

    def test_receive_requires_idempotency_key(self):
        purchase = self.create().data
        response = self.client.post(
            f"/api/v1/purchases/{purchase['id']}/receive/", {"lines": {self.line_id(purchase, self.shirt): "1"}}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_reverse_receipt_restores_stock_and_status(self):
        purchase = self.create().data
        received = self.receive(purchase, {self.line_id(purchase, self.shirt): "4"}).data
        receipt_id = received["receipts"][0]["id"]
        url = f"/api/v1/purchases/{purchase['id']}/receipts/{receipt_id}/reverse/"
        self.assertEqual(self.client.post(url, {"reason": ""}, format="json").status_code, 400)
        response = self.client.post(url, {"reason": "Counted wrong carton"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "open")
        self.assertEqual(self.on_hand(self.shirt), Decimal("0"))
        self.assertEqual(self.client.post(url, {"reason": "again"}, format="json").status_code, 409)

    def test_reversal_restores_previous_average_cost(self):
        branch = self.org.branches.get()
        apply_movement(
            organization=self.org,
            variant=self.shirt,
            branch=branch,
            quantity_delta=Decimal("18"),
            movement_type=StockMovement.Type.OPENING,
            actor=self.owner,
            unit_cost_base=Decimal("4.50"),
        )
        purchase = self.create().data  # shirt lands at 660 LRD = 3.30 USD
        received = self.receive(purchase, {self.line_id(purchase, self.shirt): "6"}).data
        balance = StockBalance.objects.get(variant=self.shirt)
        self.assertEqual(balance.average_cost_base, Decimal("4.2000"))  # (81 + 19.80) / 24
        url = f"/api/v1/purchases/{purchase['id']}/receipts/{received['receipts'][0]['id']}/reverse/"
        self.client.post(url, {"reason": "Entered twice"}, format="json")
        balance.refresh_from_db()
        self.assertEqual((balance.quantity, balance.average_cost_base), (Decimal("18.000"), Decimal("4.5000")))

    def test_cannot_reverse_receipt_once_stock_is_used(self):
        purchase = self.create().data
        received = self.receive(purchase, {self.line_id(purchase, self.shirt): "4"}).data
        apply_movement(
            organization=self.org,
            variant=self.shirt,
            branch=self.org.branches.get(),
            quantity_delta=Decimal("-3"),
            movement_type=StockMovement.Type.SALE,
            actor=self.owner,
        )
        url = f"/api/v1/purchases/{purchase['id']}/receipts/{received['receipts'][0]['id']}/reverse/"
        self.assertEqual(self.client.post(url, {"reason": "Wrong"}, format="json").status_code, 400)
        self.assertEqual(Purchase.objects.get().status, "partially_received")
        self.assertEqual(self.on_hand(self.shirt), Decimal("1"))

    def test_edit_and_cancel_rules(self):
        purchase = self.create().data
        url = f"/api/v1/purchases/{purchase['id']}/"
        edited = self.client.patch(url, {"shipping_cost": "0"}, format="json")
        self.assertEqual(edited.data["total"], "10000.00")
        self.receive(purchase, {self.line_id(purchase, self.shirt): "1"})
        self.assertEqual(self.client.patch(url, {"shipping_cost": "5"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(url + "cancel/", {"reason": "Supplier closed"}, format="json").status_code, 409)
        other = self.create().data
        cancelled = self.client.post(f"/api/v1/purchases/{other['id']}/cancel/", {"reason": "Duplicate"}, format="json")
        self.assertEqual(cancelled.data["status"], "cancelled")

    def test_missing_rate_blocks_lrd_purchase(self):
        # The only LRD rate starts today, so a purchase dated a month ago has none.
        response = self.create(purchase_date=(TODAY - timedelta(days=30)).isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertIn("currency", response.data["error"]["field_errors"])

    def test_line_validation(self):
        printing = self.org.sections.get(code="printing")
        paper = ensure_default_variant(Product.objects.create(organization=self.org, section=printing, name="Paper"))
        response = self.create(lines=[{"variant": str(paper.pk), "quantity": "1", "unit_cost": "1"}])
        self.assertIn("lines.0.variant", response.data["error"]["field_errors"])
        response = self.create(lines=[])
        self.assertIn("lines", response.data["error"]["field_errors"])

    def test_cashier_cannot_see_purchases(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.assertEqual(client_for(cashier).get("/api/v1/purchases/").status_code, 403)

    def test_future_purchase_date_rejected(self):
        response = self.create(purchase_date=(TODAY + timedelta(days=2)).isoformat())
        self.assertEqual(response.status_code, 400)
