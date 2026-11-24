from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.catalog.models import Customer, Product
from apps.identity.tests.factories import PASSWORD, add_member, client_for, make_org, make_user


class OrganizationIsolationTests(TestCase):
    def setUp(self):
        self.org_a, self.owner_a = make_org("Studio A", "owner_a")
        self.org_b, self.owner_b = make_org("Studio B", "owner_b")
        self.customer_b = Customer.objects.create(organization=self.org_b, name="Private B customer")

    def test_list_only_shows_own_organization(self):
        Customer.objects.create(organization=self.org_a, name="A customer")
        response = client_for(self.owner_a).get("/api/v1/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c["name"] for c in response.data["results"]], ["A customer"])

    def test_other_organization_record_is_not_found(self):
        response = client_for(self.owner_a).get(f"/api/v1/customers/{self.customer_b.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "not_found")

    def test_cannot_update_other_organization_record(self):
        response = client_for(self.owner_a).patch(f"/api/v1/customers/{self.customer_b.pk}/", {"name": "Hijacked"}, format="json")
        self.assertEqual(response.status_code, 404)
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.name, "Private B customer")

    def test_organization_header_for_foreign_org_is_denied(self):
        response = client_for(self.owner_a).get("/api/v1/customers/", HTTP_X_ORGANIZATION_ID=str(self.org_b.pk))
        self.assertEqual(response.status_code, 403)

    def test_created_record_belongs_to_callers_organization(self):
        response = client_for(self.owner_a).post("/api/v1/customers/", {"name": "New", "organization": str(self.org_b.pk)}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Customer.objects.get(pk=response.data["id"]).organization_id, self.org_a.pk)


class RoleAndSectionScopeTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        self.printing = self.org.sections.get(code="printing")
        self.shirt = Product.objects.create(organization=self.org, section=self.clothing, name="T-shirt")
        self.banner = Product.objects.create(
            organization=self.org, section=self.printing, name="Banner", kind="service", tracks_stock=False
        )

    def test_department_staff_only_sees_assigned_section(self):
        printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        response = client_for(printer).get("/api/v1/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["name"] for p in response.data["results"]], ["Banner"])
        self.assertEqual(client_for(printer).get(f"/api/v1/products/{self.shirt.pk}/").status_code, 404)

    def test_cashier_can_view_but_not_create_products(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        client = client_for(cashier)
        self.assertEqual(client.get("/api/v1/products/").status_code, 200)
        response = client.post("/api/v1/products/", {"name": "X", "section": str(self.clothing.pk)}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "permission_denied")

    def test_manager_cannot_create_product_in_unassigned_section(self):
        manager = add_member(self.org, "manager", "manager", sections=["printing"])
        response = client_for(manager).post("/api/v1/products/", {"name": "Hoodie", "section": str(self.clothing.pk)}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("section", response.data["error"]["field_errors"])

    def test_inactive_membership_is_denied(self):
        former = add_member(self.org, "former", "manager", all_sections=True, active=False)
        self.assertEqual(client_for(former).get("/api/v1/products/").status_code, 403)

    def test_user_without_membership_is_denied(self):
        self.assertEqual(client_for(make_user("stranger")).get("/api/v1/customers/").status_code, 403)

    def test_unauthenticated_gets_error_envelope_with_request_id(self):
        response = APIClient().get("/api/v1/customers/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "not_authenticated")
        self.assertEqual(response.data["error"]["request_id"], response["X-Request-ID"])


class AuditTrailTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def test_create_writes_audit_event_without_contact_details(self):
        response = client_for(self.owner).post("/api/v1/customers/", {"name": "Amara", "phone": "+231 555 0100"}, format="json")
        event = AuditEvent.objects.get(entity_id=response.data["id"])
        self.assertEqual(event.action, "customer.created")
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.summary["phone"], "[changed]")
        self.assertEqual(event.request_id, response["X-Request-ID"])

    def test_audit_events_are_append_only(self):
        client_for(self.owner).post("/api/v1/customers/", {"name": "Amara"}, format="json")
        event = AuditEvent.objects.get()
        event.action = "tampered"
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()

    def test_audit_api_is_restricted_and_scoped(self):
        other_org, other_owner = make_org("Other", "other_owner")
        client_for(other_owner).post("/api/v1/customers/", {"name": "Elsewhere"}, format="json")
        client_for(self.owner).post("/api/v1/customers/", {"name": "Here"}, format="json")
        response = client_for(self.owner).get("/api/v1/audit-events/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.assertEqual(client_for(cashier).get("/api/v1/audit-events/").status_code, 403)

    def test_invalid_date_filter_is_a_validation_error(self):
        response = client_for(self.owner).get("/api/v1/audit-events/?from=yesterday")
        self.assertEqual(response.status_code, 400)
        self.assertIn("from", response.data["error"]["field_errors"])


class SessionAuthenticationTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def _csrf_client(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        return client, token

    def test_login_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post("/api/v1/auth/login/", {"username": "owner", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_login_returns_user_and_organizations(self):
        client, token = self._csrf_client()
        response = client.post("/api/v1/auth/login/", {"username": "owner", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organizations"][0]["name"], "Studio")
        organization = client.get("/api/v1/organization/").data
        self.assertIn("audit.view", organization["permissions"])

    def test_bad_password_returns_generic_error(self):
        client, token = self._csrf_client()
        response = client.post("/api/v1/auth/login/", {"username": "owner", "password": "wrong"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["message"], "Invalid username or password.")
