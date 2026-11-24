from django.test import TestCase

from apps.identity.models import Membership
from apps.identity.tests.factories import add_member, client_for, make_org

BASE = "/api/v1/chat"


class ChatTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.other_org, self.outsider = make_org("Other", "outsider")

    def headers(self, org=None):
        return {"HTTP_X_ORGANIZATION_ID": str((org or self.org).pk)}

    def threads(self, user, org=None):
        return client_for(user).get(f"{BASE}/conversations/", **self.headers(org)).data

    def team(self, user):
        return next(r for r in self.threads(user)["results"] if r["kind"] == "team")

    def send(self, user, conversation_id, body):
        return client_for(user).post(f"{BASE}/conversations/{conversation_id}/messages/", {"body": body}, format="json", **self.headers())

    def test_team_chat_is_shared_and_counts_unread(self):
        team = self.team(self.owner)
        self.assertEqual(team["title"], "Team chat")
        self.assertEqual(self.send(self.owner, team["id"], "  Morning all  ").status_code, 201)
        self.assertEqual(self.team(self.owner)["unread"], 0)
        cashier_view = self.threads(self.cashier)
        self.assertEqual(cashier_view["unread"], 1)
        messages = client_for(self.cashier).get(f"{BASE}/conversations/{team['id']}/messages/", **self.headers()).data["results"]
        self.assertEqual([(m["body"], m["mine"]) for m in messages], [("Morning all", False)])
        client_for(self.cashier).post(f"{BASE}/conversations/{team['id']}/read/", **self.headers())
        self.assertEqual(self.threads(self.cashier)["unread"], 0)

    def test_direct_chat_is_private_to_the_pair(self):
        opened = client_for(self.owner).post(f"{BASE}/conversations/", {"user": str(self.cashier.pk)}, format="json", **self.headers())
        self.assertEqual(opened.status_code, 201)
        again = client_for(self.cashier).post(f"{BASE}/conversations/", {"user": str(self.owner.pk)}, format="json", **self.headers())
        self.assertEqual(again.data["id"], opened.data["id"])
        self.assertEqual(again.data["title"], "owner")
        self.send(self.owner, opened.data["id"], "Can you close the till?")
        self.assertEqual(self.threads(self.cashier)["unread"], 1)
        # The third person cannot see, read or post to it.
        self.assertNotIn(opened.data["id"], [r["id"] for r in self.threads(self.printer)["results"]])
        url = f"{BASE}/conversations/{opened.data['id']}/messages/"
        self.assertEqual(client_for(self.printer).get(url, **self.headers()).status_code, 404)
        self.assertEqual(self.send(self.printer, opened.data["id"], "hi").status_code, 404)

    def test_people_and_bad_requests(self):
        people = client_for(self.owner).get(f"{BASE}/people/", **self.headers()).data
        self.assertEqual({p["name"] for p in people}, {"cashier", "printer"})
        me = client_for(self.owner).post(f"{BASE}/conversations/", {"user": str(self.owner.pk)}, format="json", **self.headers())
        self.assertEqual(me.status_code, 400)
        stranger = client_for(self.owner).post(f"{BASE}/conversations/", {"user": str(self.outsider.pk)}, format="json", **self.headers())
        self.assertEqual(stranger.status_code, 400)
        team = self.team(self.owner)
        self.assertEqual(self.send(self.owner, team["id"], "   ").status_code, 400)
        self.assertEqual(self.send(self.owner, team["id"], "x" * 2001).status_code, 400)

    def test_organizations_and_deactivated_staff_are_separate(self):
        team = self.team(self.owner)
        self.send(self.owner, team["id"], "Studio only")
        outsider_team = self.team_for(self.outsider, self.other_org)
        self.assertNotEqual(outsider_team["id"], team["id"])
        self.assertIsNone(outsider_team["last_message"])
        url = f"{BASE}/conversations/{team['id']}/messages/"
        self.assertEqual(client_for(self.outsider).get(url, **self.headers(self.other_org)).status_code, 404)
        # A direct thread disappears once the other person is deactivated.
        opened = client_for(self.owner).post(f"{BASE}/conversations/", {"user": str(self.printer.pk)}, format="json", **self.headers())
        Membership.objects.filter(user=self.printer).update(active=False)
        self.assertNotIn(opened.data["id"], [r["id"] for r in self.threads(self.owner)["results"]])
        self.assertEqual(client_for(self.printer).get(f"{BASE}/conversations/", **self.headers()).status_code, 404)

    def team_for(self, user, org):
        return next(r for r in self.threads(user, org)["results"] if r["kind"] == "team")

    def test_signed_out_is_refused(self):
        self.assertIn(self.client.get(f"{BASE}/conversations/").status_code, (401, 403))
