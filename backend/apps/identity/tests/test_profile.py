from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.identity.tests.factories import client_for, make_org


class ProfileTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def test_edit_own_name_and_email(self):
        response = client_for(self.owner).patch(
            "/api/v1/auth/me/", {"first_name": " Amara ", "last_name": "Sesay", "email": "amara@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["display_name"], "Amara Sesay")
        self.assertEqual(response.data["email"], "amara@example.com")
        self.assertTrue(AuditEvent.objects.filter(action="user.profile_updated", organization=self.org).exists())

    def test_rejects_bad_email_and_ignores_other_fields(self):
        bad = client_for(self.owner).patch("/api/v1/auth/me/", {"email": "not-an-email"}, format="json")
        self.assertEqual(bad.status_code, 400)
        client_for(self.owner).patch("/api/v1/auth/me/", {"username": "boss", "is_superuser": True}, format="json")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "owner")
        self.assertFalse(self.owner.is_superuser)

    def test_signed_out_is_refused(self):
        self.assertIn(self.client.patch("/api/v1/auth/me/", {"first_name": "x"}).status_code, (401, 403))
