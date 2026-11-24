"""Public website: data exposure, booking requests, order tracking and the staff review queue."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.catalog.models import Customer, Product
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.orders.services import create_order
from apps.public_site import services
from apps.public_site.models import WebsiteProfile, WebsiteRequest

PUBLIC = "/api/public/v1"


def old_token(seconds=10):
    """A form token issued `seconds` ago (forms filled faster than a person can are rejected)."""
    past = timezone.now() - timedelta(seconds=seconds)
    with mock.patch("apps.public_site.services.timezone.now", return_value=past):
        return services.form_token()


class PublicSiteTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters
        self.org, self.owner = make_org("Studio", "owner")
        WebsiteProfile.objects.create(organization=self.org, enabled=True, headline="Smile with us", phone="0777 000 111")
        self.membership = self.owner.organization_memberships.get()
        printing = self.org.sections.get(code="printing")
        self.flyers = Product.objects.create(
            organization=self.org,
            section=printing,
            name="A5 flyers",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("45"),
            buying_price_base=Decimal("13.37"),
            show_online=True,
            public_description="Full colour, 500 pieces.",
        )
        Product.objects.create(organization=self.org, section=printing, name="Secret item", selling_price_base=Decimal("9"))
        self.customer = Customer.objects.create(organization=self.org, name="Amara Sesay", phone="+231 770 000 001")
        self.order = create_order(
            membership=self.membership,
            actor=self.owner,
            section=printing,
            branch=self.org.branches.get(),
            customer=self.customer,
            currency="USD",
            total="45.00",
            due_date=timezone.localdate() + timedelta(days=3),
            title="A5 flyers × 500",
            detail={"item": "Flyers", "quantity": "500", "size": "A5"},
        )
        self.anon = APIClient()

    def test_site_and_catalog_show_only_published_public_fields(self):
        site = self.anon.get(f"{PUBLIC}/site/").data
        self.assertEqual(site["name"], "Studio")
        self.assertEqual(site["headline"], "Smile with us")
        self.assertIn("form_token", site)
        rows = self.anon.get(f"{PUBLIC}/catalog/").data["results"]
        self.assertEqual([r["name"] for r in rows], ["A5 flyers"])
        self.assertEqual(rows[0]["price_usd"], "45.00")
        body = str(rows)
        self.assertNotIn("13.37", body)  # never the cost
        self.assertNotIn("buying", body)
        self.assertNotIn("Secret", body)

    def test_disabled_website_is_not_found(self):
        WebsiteProfile.objects.filter(organization=self.org).update(enabled=False)
        self.assertEqual(self.anon.get(f"{PUBLIC}/site/").status_code, 404)
        self.assertEqual(self.anon.get(f"{PUBLIC}/catalog/").status_code, 404)

    def test_booking_request_needs_a_real_form_and_lands_in_the_queue(self):
        body = {"kind": "photography", "name": "Musu", "phone": "0777 908 311", "message": "Wedding on Saturday", "token": old_token()}
        response = self.anon.post(f"{PUBLIC}/requests/", body, format="json")
        self.assertEqual(response.status_code, 201)
        row = WebsiteRequest.objects.get(number=response.data["number"])
        self.assertEqual((row.status, row.section.code), ("new", "photography"))
        self.assertFalse(row.organization.custom_orders.filter(title__icontains="wedding").exists())  # never an order by itself
        bot = dict(body, website="http://spam.example")
        self.assertEqual(self.anon.post(f"{PUBLIC}/requests/", bot, format="json").status_code, 400)
        too_fast = dict(body, token=services.form_token())
        self.assertEqual(self.anon.post(f"{PUBLIC}/requests/", too_fast, format="json").status_code, 400)
        forged = dict(body, token="123:abc")
        self.assertEqual(self.anon.post(f"{PUBLIC}/requests/", forged, format="json").status_code, 400)

    def test_requests_are_rate_limited(self):
        body = {"kind": "printing", "name": "A", "phone": "0777 908 311", "message": "Banner please", "token": old_token()}
        codes = [self.anon.post(f"{PUBLIC}/requests/", body, format="json").status_code for _ in range(6)]
        self.assertEqual(codes[:5], [201] * 5)
        self.assertEqual(codes[5], 429)

    def test_tracking_needs_number_and_matching_phone(self):
        ok = self.anon.post(f"{PUBLIC}/track/", {"number": self.order.number.lower(), "phone": "0770000001"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status_label"], "Pending")
        self.assertEqual(ok.data["balance_due"], "45.00")
        self.assertNotIn("Amara", str(ok.data))  # no personal details
        wrong_phone = self.anon.post(f"{PUBLIC}/track/", {"number": self.order.number, "phone": "0886 123 456"}, format="json")
        unknown = self.anon.post(f"{PUBLIC}/track/", {"number": "ORD-9999", "phone": "0770000001"}, format="json")
        self.assertEqual((wrong_phone.status_code, unknown.status_code), (404, 404))
        message = lambda r: r.data["error"]["message"]  # noqa: E731
        self.assertEqual(message(wrong_phone), message(unknown))  # no hint which part was wrong

    @override_settings()
    def test_tracking_is_rate_limited(self):
        codes = [
            self.anon.post(f"{PUBLIC}/track/", {"number": f"ORD-{i:04d}", "phone": "0770000001"}, format="json").status_code
            for i in range(21)
        ]
        self.assertEqual(codes[-1], 429)

    def test_staff_queue_accept_and_decline(self):
        row = services.create_request(
            self.org, {"kind": "printing", "name": "New Person", "phone": "0886 555 1234", "message": "Need banners", "token": old_token()}
        )
        staff = client_for(self.owner)
        listing = staff.get("/api/v1/website/requests/").data
        self.assertEqual(listing["counts"]["new"], 1)
        customer = staff.post(f"/api/v1/website/requests/{row.pk}/customer/").data
        self.assertEqual(customer["name"], "New Person")
        accepted = staff.post(f"/api/v1/website/requests/{row.pk}/accept/", {"order": str(self.order.pk)}, format="json")
        self.assertEqual(
            (accepted.status_code, accepted.data["status"], accepted.data["order_number"]), (200, "accepted", self.order.number)
        )
        again = staff.post(f"/api/v1/website/requests/{row.pk}/decline/", {"reason": "x"}, format="json")
        self.assertEqual(again.status_code, 400)
        other = services.create_request(
            self.org, {"kind": "other", "name": "B", "phone": "0886 555 9999", "message": "Hello there", "token": old_token()}
        )
        self.assertEqual(staff.post(f"/api/v1/website/requests/{other.pk}/decline/", {}, format="json").status_code, 400)
        declined = staff.post(f"/api/v1/website/requests/{other.pk}/decline/", {"reason": "Out of area"}, format="json")
        self.assertEqual(declined.data["status"], "declined")
        self.assertTrue(AuditEvent.objects.filter(action="website.request_declined").exists())

    def test_existing_customer_is_matched_by_phone(self):
        row = services.create_request(
            self.org, {"kind": "printing", "name": "Amara", "phone": "0770 000 001", "message": "More flyers", "token": old_token()}
        )
        found = client_for(self.owner).post(f"/api/v1/website/requests/{row.pk}/customer/").data
        self.assertEqual(found["id"], str(self.customer.pk))

    def test_staff_permissions_and_profile(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.assertEqual(client_for(cashier).get("/api/v1/website/requests/").status_code, 403)
        staff = client_for(self.owner)
        saved = staff.put("/api/v1/website/profile/", {"headline": "New look", "map_url": "javascript:alert(1)"}, format="json")
        self.assertEqual(saved.status_code, 400)
        saved = staff.put("/api/v1/website/profile/", {"headline": "New look", "enabled": True}, format="json")
        self.assertEqual(saved.data["headline"], "New look")
        self.assertEqual(self.anon.get(f"{PUBLIC}/site/").data["headline"], "New look")
