from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.identity.models import Membership, Role
from apps.identity.tests.factories import PASSWORD, add_member, client_for, make_org

User = get_user_model()


class StaffTests(TestCase):
    def setUp(self):
        cache.clear()  # the login throttle (5/minute) is shared across tests
        self.org, self.owner = make_org("Studio", "owner")
        self.manager = add_member(self.org, "manager", "manager", all_sections=True)
        self.role = {r.code: r for r in Role.objects.filter(organization=self.org)}
        self.sections = {s.code: s for s in self.org.sections.all()}

    def add(self, user=None, **overrides):
        body = {
            "username": "musu",
            "first_name": "Musu",
            "last_name": "Kamara",
            "role": str(self.role["department-staff"].pk),
            "all_sections": False,
            "sections": [str(self.sections["printing"].pk)],
            **overrides,
        }
        return client_for(user or self.owner).post("/api/v1/staff/", body, format="json")

    def login(self, username, password):
        client = APIClient(enforce_csrf_checks=False)
        return client, client.post("/api/v1/auth/login/", {"username": username, "password": password}, format="json")

    def test_owner_adds_staff_with_temporary_password_and_scope(self):
        response = self.add()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            (response.data["role_code"], response.data["section_ids"]), ("department-staff", [str(self.sections["printing"].pk)])
        )
        temp = response.data["temporary_password"]
        client, login = self.login("musu", temp)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(client.get("/api/v1/organization/").data["section_ids"], [str(self.sections["printing"].pk)])
        self.assertTrue(AuditEvent.objects.filter(action="staff.created").exists())
        self.assertNotIn("temporary_password", client_for(self.owner).get(f"/api/v1/staff/{response.data['id']}/").data)

    def test_validation(self):
        self.add()
        self.assertIn("username", self.add().data["error"]["field_errors"])  # taken
        self.assertIn("username", self.add(username="musu k").data["error"]["field_errors"])  # spaces
        self.assertIn("sections", self.add(username="ben", sections=[]).data["error"]["field_errors"])
        self.assertIn("password", self.add(username="ben", password="12345678").data["error"]["field_errors"])
        self.assertIn("first_name", self.add(username="ben", first_name="").data["error"]["field_errors"])

    def test_only_staff_managers_can_manage(self):
        self.assertEqual(self.add(user=self.manager).status_code, 403)
        self.assertEqual(client_for(self.manager).get("/api/v1/staff/").status_code, 403)

    def test_role_and_scope_change_takes_effect(self):
        staff = self.add().data
        update = client_for(self.owner).patch(
            f"/api/v1/staff/{staff['id']}/", {"role": str(self.role["cashier"].pk), "all_sections": True}, format="json"
        )
        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual((update.data["role_code"], update.data["all_sections"], update.data["section_ids"]), ("cashier", True, []))
        user = User.objects.get(username="musu")
        self.assertEqual(client_for(user).get("/api/v1/sales/").status_code, 200)
        self.assertEqual(client_for(user).get("/api/v1/orders/", {"view": "all"}).status_code, 200)
        event = AuditEvent.objects.filter(action="staff.updated").latest("created_at")
        self.assertEqual(event.summary["changes"]["role"], ["department-staff", "cashier"])

    def test_deactivation_blocks_access_and_keeps_history(self):
        staff = self.add().data
        client, _ = self.login("musu", staff["temporary_password"])
        self.assertEqual(client.get("/api/v1/organization/").status_code, 200)
        response = client_for(self.owner).post(f"/api/v1/staff/{staff['id']}/deactivate/", {"reason": "Left the business"}, format="json")
        self.assertEqual(response.data["active"], False)
        self.assertIn(client.get("/api/v1/organization/").status_code, (401, 403))  # existing session stops working
        _, again = self.login("musu", staff["temporary_password"])
        self.assertEqual(again.status_code, 400)
        self.assertTrue(User.objects.filter(username="musu").exists())  # never deleted
        reactivated = client_for(self.owner).post(f"/api/v1/staff/{staff['id']}/reactivate/", format="json")
        self.assertEqual(reactivated.data["active"], True)
        _, back = self.login("musu", staff["temporary_password"])
        self.assertEqual(back.status_code, 200)

    def test_owner_safeguards(self):
        me = Membership.objects.get(user=self.owner)
        self.assertEqual(client_for(self.owner).post(f"/api/v1/staff/{me.pk}/deactivate/", format="json").status_code, 409)
        self.assertEqual(
            client_for(self.owner).patch(f"/api/v1/staff/{me.pk}/", {"role": str(self.role["manager"].pk)}, format="json").status_code, 409
        )
        second = self.add(username="ama", role=str(self.role["owner-admin"].pk), all_sections=True).data
        # With a second owner, the first can be deactivated by the second.
        other = User.objects.get(username="ama")
        self.assertEqual(client_for(other).post(f"/api/v1/staff/{me.pk}/deactivate/", format="json").status_code, 200)
        self.assertEqual(client_for(other).post(f"/api/v1/staff/{second['id']}/deactivate/", format="json").status_code, 409)

    def test_reset_password_signs_out_and_change_password(self):
        staff = self.add().data
        client, _ = self.login("musu", staff["temporary_password"])
        reset = client_for(self.owner).post(f"/api/v1/staff/{staff['id']}/reset-password/", format="json").data
        self.assertNotEqual(reset["temporary_password"], staff["temporary_password"])
        self.assertIn(client.get("/api/v1/organization/").status_code, (401, 403))
        client, _ = self.login("musu", reset["temporary_password"])
        wrong = client.post("/api/v1/auth/password/", {"current_password": "nope", "new_password": "Brand-new-pass-77"}, format="json")
        self.assertIn("current_password", wrong.data["error"]["field_errors"])
        ok = client.post(
            "/api/v1/auth/password/", {"current_password": reset["temporary_password"], "new_password": "Brand-new-pass-77"}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(client.get("/api/v1/organization/").status_code, 200)  # this session survives
        self.assertTrue(AuditEvent.objects.filter(action="auth.password_changed").exists())

    def test_login_is_audited(self):
        self.login("owner", PASSWORD)
        self.assertTrue(AuditEvent.objects.filter(action="auth.login", actor=self.owner).exists())


class RoleTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def test_custom_role_lifecycle(self):
        client = client_for(self.owner)
        catalog = client.get("/api/v1/roles/catalog/").data
        self.assertIn("Department orders", [g["title"] for g in catalog])
        created = client.post(
            "/api/v1/roles/", {"name": "Senior cashier", "permissions": ["sales.view", "sales.create", "sales.reverse"]}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["code"], "senior-cashier")
        updated = client.patch(f"/api/v1/roles/{created.data['id']}/", {"permissions": ["sales.view", "sales.create"]}, format="json")
        self.assertEqual(updated.data["permissions"], ["sales.create", "sales.view"])
        self.assertEqual(AuditEvent.objects.get(action="role.updated").summary["removed"], ["sales.reverse"])
        system = Role.objects.get(organization=self.org, code="cashier")
        self.assertEqual(client.patch(f"/api/v1/roles/{system.pk}/", {"permissions": ["sales.view"]}, format="json").status_code, 409)
        self.assertEqual(client.post("/api/v1/roles/", {"name": "x", "permissions": ["made.up"]}, format="json").status_code, 400)
        self.assertEqual(
            client.post("/api/v1/roles/", {"name": "Senior Cashier", "permissions": ["sales.view"]}, format="json").status_code, 400
        )
