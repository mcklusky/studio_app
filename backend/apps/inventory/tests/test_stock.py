from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Product, ProductVariant
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import InsufficientStock, adjust_stock, apply_movement, ensure_default_variant, reconcile


class StockServiceTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.branch = self.org.branches.get()
        self.product = Product.objects.create(organization=self.org, section=self.org.sections.get(code="clothing"), name="T-shirt")
        self.variant = ensure_default_variant(self.product)

    def move(self, delta, cost=None, kind=StockMovement.Type.ADJUSTMENT):
        return apply_movement(
            organization=self.org,
            variant=self.variant,
            branch=self.branch,
            quantity_delta=Decimal(delta),
            movement_type=kind,
            actor=self.owner,
            unit_cost_base=None if cost is None else Decimal(cost),
        )

    def balance(self):
        return StockBalance.objects.get(variant=self.variant, branch=self.branch)

    def test_weighted_average_cost(self):
        self.move("10", "2.00", StockMovement.Type.OPENING)
        self.move("10", "4.00", StockMovement.Type.RECEIPT)
        self.assertEqual(self.balance().average_cost_base, Decimal("3.0000"))
        out = self.move("-5")
        self.assertEqual(out.unit_cost_base, Decimal("3.0000"))
        balance = self.balance()
        self.assertEqual((balance.quantity, balance.average_cost_base), (Decimal("15.000"), Decimal("3.0000")))

    def test_inbound_without_cost_keeps_average(self):
        self.move("4", "5.00")
        self.move("2")  # e.g. a customer return
        self.assertEqual(self.balance().average_cost_base, Decimal("5.0000"))

    def test_cannot_go_below_zero_and_nothing_is_written(self):
        self.move("3", "1.00")
        with self.assertRaises(InsufficientStock):
            self.move("-4")
        self.assertEqual(self.balance().quantity, Decimal("3.000"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_ledger_reconciles_to_balance(self):
        for delta, cost in (("10", "2"), ("-3", None), ("5", "2.5"), ("-1.5", None)):
            self.move(delta, cost)
        balance, ledger = reconcile(self.variant, self.branch)
        self.assertEqual(balance, ledger)
        self.assertEqual(balance, Decimal("10.500"))

    def test_service_products_cannot_hold_stock(self):
        self.product.tracks_stock = False
        self.product.save()
        self.variant.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.move("1", "1")

    def test_movements_are_append_only(self):
        movement = self.move("1", "1")
        movement.reason = "edited"
        with self.assertRaises(ValueError):
            movement.save()
        with self.assertRaises(ValueError):
            movement.delete()

    def test_database_rejects_negative_balance(self):
        self.move("1", "1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockBalance.objects.filter(variant=self.variant).update(quantity=Decimal("-1"))

    def test_adjustment_reason_rules(self):
        cases = [
            {"quantity_delta": "5", "reason": "damage"},
            {"quantity_delta": "5", "reason": "opening"},
            {"quantity_delta": "-1", "reason": "other"},
            {"quantity_delta": "1", "reason": "made-up"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                adjust_stock(
                    organization=self.org,
                    variant=self.variant,
                    branch=self.branch,
                    actor=self.owner,
                    quantity_delta=Decimal(case["quantity_delta"]),
                    reason=case["reason"],
                )
        self.assertFalse(StockMovement.objects.exists())


class StockApiTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        self.printing = self.org.sections.get(code="printing")
        client = client_for(self.owner)
        self.shirt = client.post(
            "/api/v1/products/",
            {"name": "T-shirt", "section": str(self.clothing.pk), "minimum_stock": "5", "buying_price_base": "3.00"},
            format="json",
        ).data
        self.paper = client.post(
            "/api/v1/products/", {"name": "A4 paper", "section": str(self.printing.pk), "minimum_stock": "2"}, format="json"
        ).data
        self.shirt_variant = self.shirt["variants"][0]["id"]
        self.paper_variant = self.paper["variants"][0]["id"]

    def adjust(self, user, variant, delta, reason="opening", cost="2.00", **extra):
        body = {"variant": variant, "quantity_delta": delta, "reason": reason, "unit_cost_base": cost, **extra}
        return client_for(user).post(
            "/api/v1/stock-adjustments/", body, format="json", **{k: v for k, v in extra.items() if k.startswith("HTTP_")}
        )

    def test_product_create_makes_default_variant(self):
        self.assertEqual([v["code"] for v in self.shirt["variants"]], ["default"])

    def test_first_real_option_retires_unused_default(self):
        client_for(self.owner).post("/api/v1/product-variants/", {"product": self.shirt["id"], "code": "M", "size": "M"}, format="json")
        variants = {v.code: v.active for v in ProductVariant.objects.filter(product_id=self.shirt["id"])}
        self.assertEqual(variants, {"default": False, "M": True})

    def test_opening_stock_and_levels(self):
        response = self.adjust(self.owner, self.shirt_variant, "12")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity_after"], "12.000")
        levels = client_for(self.owner).get("/api/v1/stock/").data
        shirt = next(r for r in levels["results"] if r["variant_id"] == self.shirt_variant)
        self.assertEqual((shirt["on_hand"], shirt["status"], shirt["stock_value_base"]), ("12", "ok", "24.00"))
        self.assertEqual(levels["total_value_base"], "24.00")
        self.assertEqual(levels["valuation_basis"], "moving_weighted_average")

    def test_low_and_out_filters(self):
        self.adjust(self.owner, self.shirt_variant, "4")  # minimum 5 -> low; paper never stocked -> out
        client = client_for(self.owner)
        self.assertEqual([r["label"] for r in client.get("/api/v1/stock/?status=low").data["results"]], ["T-shirt"])
        self.assertEqual([r["label"] for r in client.get("/api/v1/stock/?status=out").data["results"]], ["A4 paper"])
        self.assertEqual(client.get("/api/v1/stock/?status=bogus").status_code, 400)

    def test_removing_more_than_on_hand_is_rejected(self):
        self.adjust(self.owner, self.shirt_variant, "2")
        response = self.adjust(self.owner, self.shirt_variant, "-3", reason="damage", cost=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity_delta", response.data["error"]["field_errors"])

    def test_idempotent_adjustment_is_not_applied_twice(self):
        for _ in range(2):
            response = self.adjust(self.owner, self.shirt_variant, "5", HTTP_IDEMPOTENCY_KEY="count-1")
            self.assertEqual(response.status_code, 201)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_cashier_cannot_adjust(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.assertEqual(self.adjust(cashier, self.shirt_variant, "5").status_code, 403)

    def test_staff_without_cost_access_see_quantities_only(self):
        self.adjust(self.owner, self.paper_variant, "10")
        printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        client = client_for(printer)
        levels = client.get("/api/v1/stock/").data
        self.assertEqual([r["label"] for r in levels["results"]], ["A4 paper"])
        self.assertNotIn("stock_value_base", levels["results"][0])
        self.assertNotIn("total_value_base", levels)
        movement = client.get("/api/v1/stock-movements/").data["results"][0]
        self.assertNotIn("unit_cost_base", movement)
        self.assertNotIn("buying_price_base", client.get(f"/api/v1/products/{self.paper['id']}/").data)

    def test_cannot_adjust_product_outside_section(self):
        manager = add_member(self.org, "manager", "manager", sections=["printing"])
        response = self.adjust(manager, self.shirt_variant, "5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("variant", response.data["error"]["field_errors"])

    def test_cannot_stop_tracking_with_stock_on_hand(self):
        self.adjust(self.owner, self.shirt_variant, "1")
        response = client_for(self.owner).patch(f"/api/v1/products/{self.shirt['id']}/", {"tracks_stock": False}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_adjustment_writes_audit_event(self):
        from apps.audit.models import AuditEvent

        self.adjust(self.owner, self.shirt_variant, "3")
        self.assertTrue(AuditEvent.objects.filter(action="stock.adjusted").exists())
