from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.catalog.models import Customer
from apps.common.idempotency import run_idempotent
from apps.common.models import IdempotencyRecord
from apps.identity.tests.factories import make_org


class CreateCustomerView(APIView):
    """Minimal retry-safe write used to exercise run_idempotent."""

    organization = None
    fail = False

    def post(self, request):
        def handler():
            customer = Customer.objects.create(organization=self.organization, name=request.data["name"])
            if self.fail:
                raise RuntimeError("simulated failure after write")
            return Response({"id": str(customer.pk)}, status=201)

        return run_idempotent(request, organization=self.organization, scope="test.customer", handler=handler)


class IdempotencyTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.factory = APIRequestFactory()

    def post(self, body, key="key-1", fail=False):
        request = self.factory.post("/test/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
        force_authenticate(request, user=self.owner)
        return CreateCustomerView.as_view(organization=self.org, fail=fail)(request)

    def test_same_key_and_body_replays_without_second_write(self):
        first = self.post({"name": "Amara"})
        second = self.post({"name": "Amara"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.data, first.data)
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(Customer.objects.count(), 1)

    def test_same_key_with_different_body_conflicts(self):
        self.post({"name": "Amara"})
        response = self.post({"name": "Someone else"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Customer.objects.count(), 1)

    def test_failed_handler_rolls_back_and_key_can_be_retried(self):
        with self.assertLogs("apps.common.exceptions", level="ERROR"):
            failed = self.post({"name": "Amara"}, fail=True)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.data["error"]["code"], "server_error")
        self.assertEqual(Customer.objects.count(), 0)
        self.assertFalse(IdempotencyRecord.objects.exists())
        self.assertEqual(self.post({"name": "Amara"}).status_code, 201)
