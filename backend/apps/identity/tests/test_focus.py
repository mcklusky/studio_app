"""Top-bar section/branch focus (X-Section-ID / X-Branch-ID): narrows reads, never widens access, never blocks writes."""

from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Product
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant


class FocusTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.branch = self.org.branches.get()
        self.clothing = self.org.sections.get(code="clothing")
        self.printing = self.org.sections.get(code="printing")
        self.products = {}
        for section in (self.clothing, self.printing):
            product = Product.objects.create(
                organization=self.org, section=section, name=f"{section.name} item", selling_price_base=Decimal("10")
            )
            apply_movement(
                organization=self.org,
                variant=ensure_default_variant(product),
                branch=self.branch,
                quantity_delta=Decimal("10"),
                movement_type=StockMovement.Type.OPENING,
                actor=self.owner,
                unit_cost_base=Decimal("4"),
            )
            self.products[section.code] = product
        for i, code in enumerate(("clothing", "printing", "printing")):
            self.sell(self.owner, code, key=f"seed-{i}")

    def sell(self, user, code, key, **headers):
        section = self.clothing if code == "clothing" else self.printing
        body = {
            "section": str(section.pk),
            "currency": "USD",
            "items": [{"product": str(self.products[code].pk), "quantity": "1"}],
            "payment": {"amount": "10.00", "method": "cash"},
        }
        return client_for(user).post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY=key, **headers)

    def numbers(self, user, **headers):
        return client_for(user).get("/api/v1/sales/", **headers).data["count"]

    def test_focus_narrows_lists_dashboard_and_search(self):
        self.assertEqual(self.numbers(self.owner), 3)
        printing = {"HTTP_X_SECTION_ID": str(self.printing.pk)}
        self.assertEqual(self.numbers(self.owner, **printing), 2)
        self.assertEqual(self.numbers(self.owner, HTTP_X_BRANCH_ID=str(self.branch.pk)), 3)
        dashboard = client_for(self.owner).get("/api/v1/reports/dashboard/", **printing).data
        self.assertEqual(dashboard["figures"]["sales"]["count"], 2)
        results = client_for(self.owner).get("/api/v1/search/", {"q": "item"}, **printing).data
        names = [row["title"] for group in results["groups"] for row in group["results"] if group["key"] == "products"]
        self.assertEqual(names, ["Printing item"])

    def test_focus_never_widens_scope(self):
        tailor = add_member(self.org, "tailor", "cashier", sections=["clothing"])
        self.assertEqual(self.numbers(tailor), 1)
        # Asking for a section outside the person's scope is ignored, not honoured.
        self.assertEqual(self.numbers(tailor, HTTP_X_SECTION_ID=str(self.printing.pk)), 1)
        self.assertEqual(self.numbers(tailor, HTTP_X_SECTION_ID="not-a-uuid"), 1)
        other_org, other_owner = make_org("Other", "other")
        self.assertEqual(self.numbers(other_owner, HTTP_X_SECTION_ID=str(self.clothing.pk)), 0)

    def test_writes_ignore_focus(self):
        response = self.sell(self.owner, "clothing", key="w1", HTTP_X_SECTION_ID=str(self.printing.pk))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(str(response.data["section"]), str(self.clothing.pk))
