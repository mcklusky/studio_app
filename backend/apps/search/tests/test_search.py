from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Customer, Product, Supplier
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.services import adjust_stock, ensure_default_variant
from apps.notifications.models import AlertRead
from apps.orders.models import CustomOrder
from apps.sales.models import Sale

TODAY = timezone.localdate()


class Base(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.sec = {s.code: s for s in self.org.sections.all()}
        self.customer = Customer.objects.create(organization=self.org, name="Amara Sesay", phone="0770 111 222")
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.keys = iter(range(1000))

    def order(self, section="printing", due=None, user=None, **extra):
        body = {
            "section": str(self.sec[section].pk),
            "customer": str(self.customer.pk),
            "currency": "USD",
            "total": "50",
            "due_date": (due or TODAY + timedelta(days=7)).isoformat(),
            "detail": {"item": "Banner", "quantity": "1"},
            **extra,
        }
        if section == "clothing":
            body.update(detail={"item": "Jersey"}, items=[{"size": "M"}])
        response = client_for(user or self.owner).post("/api/v1/orders/", body, format="json", HTTP_IDEMPOTENCY_KEY=f"o{next(self.keys)}")
        assert response.status_code == 201, response.data
        return response.data


class SearchTests(Base):
    def search(self, user, q):
        response = client_for(user).get("/api/v1/search/", {"q": q})
        assert response.status_code == 200, response.data
        return {g["key"]: g for g in response.data["groups"]}

    def test_groups_respect_permissions(self):
        Supplier.objects.create(organization=self.org, name="Amara Wholesale")
        self.order()
        owner = self.search(self.owner, "amara")
        self.assertTrue({"customers", "suppliers", "orders"} <= set(owner))
        cashier = self.search(self.cashier, "amara")
        self.assertIn("customers", cashier)
        self.assertNotIn("suppliers", cashier)  # cashiers cannot see suppliers
        self.assertNotIn("staff", self.search(self.cashier, "printer"))
        self.assertIn("staff", self.search(self.owner, "printer"))

    def test_section_scope(self):
        clothing = self.order("clothing")
        printing = self.order("printing")
        found = [r["id"] for r in self.search(self.printer, "ORD-")["orders"]["results"]]
        self.assertEqual(found, [printing["id"]])
        self.assertNotIn(clothing["id"], found)

    def test_number_phone_and_short_queries(self):
        order = self.order()
        self.assertEqual(self.search(self.owner, order["number"])["orders"]["results"][0]["id"], order["id"])
        self.assertIn("customers", self.search(self.owner, "111 222"))
        self.assertEqual(client_for(self.owner).get("/api/v1/search/", {"q": "a"}).data["groups"], [])

    def test_more_flag_and_cap(self):
        for i in range(7):
            Customer.objects.create(organization=self.org, name=f"Ama {i}")
        group = self.search(self.owner, "ama")["customers"]
        self.assertEqual((len(group["results"]), group["more"]), (5, True))

    def test_other_organizations_never_match(self):
        other, _ = make_org("Other", "other_owner")
        Customer.objects.create(organization=other, name="Amara Elsewhere")
        names = [r["title"] for r in self.search(self.owner, "amara")["customers"]["results"]]
        self.assertEqual(names, ["Amara Sesay"])


class AlertTests(Base):
    def alerts(self, user):
        response = client_for(user).get("/api/v1/alerts/")
        assert response.status_code == 200, response.data
        return response.data

    def test_order_due_boundaries_and_scope(self):
        late = self.order()
        CustomOrder.objects.filter(pk=late["id"]).update(due_date=TODAY - timedelta(days=2))
        self.order(due=TODAY)
        self.order(due=TODAY + timedelta(days=1))
        self.order(due=TODAY + timedelta(days=2))  # not yet
        self.order("clothing", due=TODAY)  # other section
        printer = self.alerts(self.printer)["items"]
        kinds = sorted(a["kind"] for a in printer)
        self.assertEqual(kinds, ["order_due", "order_due", "order_overdue"])
        self.assertEqual(printer[0]["kind"], "order_overdue")  # critical first
        self.assertEqual(printer[0]["link"], {"page": "orders", "id": late["id"], "query": None})
        self.assertEqual(len([a for a in self.alerts(self.owner)["items"] if a["kind"].startswith("order")]), 4)

    def test_stock_alerts_need_inventory_permission(self):
        tee = ensure_default_variant(
            Product.objects.create(organization=self.org, section=self.sec["clothing"], name="Tee", minimum_stock=Decimal("5"))
        )
        adjust_stock(
            organization=self.org,
            variant=tee,
            branch=self.org.branches.first(),
            quantity_delta=2,
            reason="opening",
            actor=self.owner,
            unit_cost_base=Decimal("1"),
        )
        ensure_default_variant(Product.objects.create(organization=self.org, section=self.sec["clothing"], name="Cap"))
        kinds = {a["kind"]: a["title"] for a in self.alerts(self.owner)["items"]}
        self.assertEqual((kinds["stock_low"], kinds["stock_out"]), ("Tee is running low", "Cap is out of stock"))
        self.assertFalse(any(a["kind"].startswith("stock") for a in self.alerts(self.cashier)["items"]))  # no inventory.view
        self.assertFalse(any(a["kind"].startswith("stock") for a in self.alerts(self.printer)["items"]))  # clothing not in scope

    def test_old_receivables_and_fx(self):
        service = Product.objects.create(
            organization=self.org,
            section=self.sec["clothing"],
            name="Fee",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("10"),
        )
        sale = (
            client_for(self.owner)
            .post(
                "/api/v1/sales/",
                {
                    "section": str(self.sec["clothing"].pk),
                    "currency": "USD",
                    "customer": str(self.customer.pk),
                    "items": [{"product": str(service.pk), "quantity": "1"}],
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="s1",
            )
            .data
        )
        self.assertFalse(any(a["kind"] == "receivable" for a in self.alerts(self.owner)["items"]))  # too recent
        Sale.objects.filter(pk=sale["id"]).update(posted_at=timezone.now() - timedelta(days=20))
        receivable = next(a for a in self.alerts(self.owner)["items"] if a["kind"] == "receivable")
        self.assertEqual(receivable["title"], "Amara Sesay owes USD 10.00")
        self.assertTrue(any(a["kind"] == "fx_rate" for a in self.alerts(self.owner)["items"]))  # no rate yet
        self.assertFalse(any(a["kind"] == "fx_rate" for a in self.alerts(self.cashier)["items"]))

    def test_read_state(self):
        self.order(due=TODAY)
        data = self.alerts(self.printer)
        self.assertEqual(data["unread"], 1)
        key = data["items"][0]["key"]
        client_for(self.printer).post("/api/v1/alerts/read/", {"keys": [key]}, format="json")
        self.assertEqual(self.alerts(self.printer)["unread"], 0)
        self.assertEqual(self.alerts(self.owner)["unread"], 2)  # per person (owner also sees the fx alert)
        client_for(self.owner).post("/api/v1/alerts/read/", {"all": True}, format="json")
        self.assertEqual(self.alerts(self.owner)["unread"], 0)
        # A changed situation (new due date) is a new, unread alert.
        CustomOrder.objects.update(due_date=TODAY + timedelta(days=1))
        self.assertEqual(self.alerts(self.printer)["unread"], 1)
        self.assertEqual(AlertRead.objects.filter(user=self.printer).count(), 1)
