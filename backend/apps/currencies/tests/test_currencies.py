"""Exchange rates and FX snapshots: lookup by date, half-up rounding, append-only rates, and
posted transactions that never change when a newer rate is entered."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditEvent
from apps.catalog.models import Product
from apps.currencies.models import ExchangeRate
from apps.currencies.services import FxSnapshot, current_rate, snapshot_for
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant
from apps.sales.models import Sale

TODAY = timezone.localdate()


class SnapshotMathTests(TestCase):
    def test_base_amount_rounds_half_up_to_cents(self):
        lrd = FxSnapshot("LRD", Decimal("200"), TODAY)
        self.assertEqual(lrd.to_base("1"), Decimal("0.01"))  # 0.005 rounds up, not to even
        self.assertEqual(lrd.to_base("3"), Decimal("0.02"))  # 0.015 -> 0.02
        self.assertEqual(FxSnapshot("LRD", Decimal("190"), TODAY).to_base("1000"), Decimal("5.26"))  # 5.263...
        self.assertEqual(FxSnapshot("LRD", Decimal("190.5"), TODAY).to_base("19050"), Decimal("100.00"))
        self.assertEqual(lrd.rate_to_base, Decimal("0.00500000"))

    def test_usd_needs_no_rate(self):
        org, _ = make_org("Studio", "owner")
        usd = snapshot_for(org, "USD", TODAY)
        self.assertEqual((usd.units_per_usd, usd.rate_date, usd.to_base("12.345")), (Decimal("1"), None, Decimal("12.35")))


class RateLookupTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.other_org, other_owner = make_org("Other", "other")
        ExchangeRate.objects.create(
            organization=self.other_org, currency="LRD", units_per_usd=Decimal("999"), effective_date=TODAY, created_by=other_owner
        )

    def rate(self, units, days_ago=0):
        return ExchangeRate.objects.create(
            organization=self.org,
            currency="LRD",
            units_per_usd=Decimal(units),
            effective_date=TODAY - timedelta(days=days_ago),
            created_by=self.owner,
        )

    def test_missing_rate_blocks_lrd_with_a_clear_message(self):
        with self.assertRaisesMessage(ValidationError, "No LRD exchange rate"):
            snapshot_for(self.org, "LRD", TODAY)  # the other organization's rate is never used
        with self.assertRaises(ValidationError):
            snapshot_for(self.org, "EUR", TODAY)

    def test_uses_latest_rate_on_or_before_the_date(self):
        self.rate("185", days_ago=10)
        self.rate("190", days_ago=3)
        self.rate("195", days_ago=-1)  # tomorrow: not yet in force
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY).units_per_usd, Decimal("190"))
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY - timedelta(days=5)).units_per_usd, Decimal("185"))
        self.assertEqual(snapshot_for(self.org, "LRD", TODAY - timedelta(days=5)).rate_date, TODAY - timedelta(days=10))
        with self.assertRaises(ValidationError):
            snapshot_for(self.org, "LRD", TODAY - timedelta(days=11))

    def test_same_day_correction_supersedes_and_rates_are_append_only(self):
        wrong = self.rate("1900")
        self.rate("190")
        self.assertEqual(current_rate(self.org, "LRD", TODAY).units_per_usd, Decimal("190"))
        wrong.units_per_usd = Decimal("191")
        with self.assertRaisesMessage(ValueError, "append-only"):
            wrong.save()


class RateApiTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.url = "/api/v1/exchange-rates/"

    def post(self, user, **body):
        return client_for(user).post(self.url, {"units_per_usd": "190", "effective_date": TODAY.isoformat(), **body}, format="json")

    def test_only_fx_managers_enter_rates_and_entries_are_audited(self):
        self.assertEqual(self.post(self.cashier).status_code, 403)
        created = self.post(self.owner, note="Central bank mid-rate")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(AuditEvent.objects.filter(action="exchange_rate.created", entity_id=created.data["id"]).exists())
        current = client_for(self.cashier).get(self.url + "current/").data  # everyone can read
        self.assertEqual(current["rates"]["LRD"], {"units_per_usd": "190.000000", "effective_date": TODAY.isoformat(), "is_today": True})

    def test_rejects_bad_rates_and_offers_no_edit_or_delete(self):
        self.assertEqual(self.post(self.owner, units_per_usd="0").status_code, 400)
        self.assertEqual(self.post(self.owner, effective_date=(TODAY + timedelta(days=2)).isoformat()).status_code, 400)
        self.assertEqual(self.post(self.owner, currency="USD").status_code, 400)
        rate_id = self.post(self.owner).data["id"]
        client = client_for(self.owner)
        self.assertEqual(client.put(f"{self.url}{rate_id}/", {"units_per_usd": "1"}, format="json").status_code, 404)
        self.assertEqual(client.delete(f"{self.url}{rate_id}/").status_code, 404)
        self.assertEqual(ExchangeRate.objects.get().units_per_usd, Decimal("190"))


class PostedSnapshotTests(TestCase):
    """Transactions in both currencies on the same day keep their own snapshot forever."""

    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.section = self.org.sections.get(code="clothing")
        shirt = Product.objects.create(organization=self.org, section=self.section, name="Shirt", selling_price_base=Decimal("12.00"))
        apply_movement(
            organization=self.org,
            variant=ensure_default_variant(shirt),
            branch=self.org.branches.get(),
            quantity_delta=Decimal("10"),
            movement_type=StockMovement.Type.OPENING,
            actor=self.owner,
            unit_cost_base=Decimal("5.00"),
        )
        self.shirt = shirt
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("190"), effective_date=TODAY, created_by=self.owner
        )

    def sell(self, currency, key, paid):
        body = {
            "section": str(self.section.pk),
            "currency": currency,
            "items": [{"product": str(self.shirt.pk), "quantity": "1"}],
            "payment": {"amount": paid, "method": "cash"},
        }
        return client_for(self.owner).post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_new_rate_never_changes_posted_sales(self):
        lrd = self.sell("LRD", "s1", "2280.00").data
        usd = self.sell("USD", "s2", "12.00").data
        self.assertEqual((lrd["total"], lrd["base_total"], usd["total"], usd["base_total"]), ("2280.00", "12.00", "12.00", "12.00"))
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("200"), effective_date=TODAY, created_by=self.owner
        )
        first = Sale.objects.get(pk=lrd["id"])
        self.assertEqual((first.fx_units_per_usd, first.base_total), (Decimal("190.000000"), Decimal("12.00")))
        later = self.sell("LRD", "s3", "2400.00").data  # priced from the catalog at the new rate
        self.assertEqual((later["total"], later["base_total"]), ("2400.00", "12.00"))
        summary = client_for(self.owner).get("/api/v1/reports/summary/").data
        sales = summary["figures"]["sales"]
        # LRD and USD kept apart; the consolidated USD total uses each sale's own saved rate (12 + 12 + 12)
        self.assertEqual((sales["by_currency"], sales["base"], sales["count"]), ({"LRD": "4680.00", "USD": "12.00"}, "36.00", 3))
