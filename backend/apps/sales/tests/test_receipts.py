"""PDF receipts: totals and payments match the sale, access follows sale scope, costs never appear."""

import re
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from reportlab import rl_config

from apps.audit.models import AuditEvent
from apps.catalog.models import Customer, Product
from apps.currencies.models import ExchangeRate
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant


class ReceiptPdfTests(TestCase):
    def setUp(self):
        self._compression = rl_config.pageCompression
        rl_config.pageCompression = 0  # keep the text readable in the PDF bytes
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        shirt = Product.objects.create(
            organization=self.org, section=self.clothing, name="Smile Tee", selling_price_base=Decimal("1200.00")
        )
        apply_movement(
            organization=self.org,
            variant=ensure_default_variant(shirt),
            branch=self.org.branches.get(),
            quantity_delta=Decimal("10"),
            movement_type=StockMovement.Type.OPENING,
            actor=self.owner,
            unit_cost_base=Decimal("313.37"),
        )
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("190"), effective_date=timezone.localdate(), created_by=self.owner
        )
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        customer = Customer.objects.create(organization=self.org, name="Amara Sesay")
        body = {
            "section": str(self.clothing.pk),
            "currency": "USD",
            "customer": str(customer.pk),
            "items": [{"product": str(shirt.pk), "quantity": "2"}],
            "payment": {"amount": "1500.00", "method": "cash", "amount_tendered": "1600.00"},
        }
        self.sale = client_for(self.cashier).post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY="r1").data
        self.url = f"/api/v1/sales/{self.sale['id']}/receipt/"

    def tearDown(self):
        rl_config.pageCompression = self._compression

    def test_pdf_shows_the_sale_and_never_costs(self):
        response = client_for(self.owner).get(self.url)  # owner can see costs on screen, but never on a receipt
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="receipt-INV-0001.pdf"')
        self.assertEqual(response["Cache-Control"], "private, no-store")
        pdf = response.content
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type /Page[^s]", pdf)), 1)  # one continuous strip, never split
        for text in (
            b"INV-0001",
            b"Amara Sesay",
            b"Smile Tee",
            b"USD 2,400.00",
            b"USD 1,500.00",
            b"USD 900.00",
            b"USD 1,600.00",
            b"USD 100.00",
        ):
            self.assertIn(text, pdf)
        for secret in (b"313.37", b"626.74", b"cost", b"profit"):
            self.assertNotIn(secret, pdf.lower())
        self.assertTrue(AuditEvent.objects.filter(action="sale.receipt_downloaded", entity_id=self.sale["id"]).exists())

    def test_reversed_sale_receipt_is_marked_void(self):
        manager = add_member(self.org, "manager", "manager", all_sections=True)
        reversed_ = client_for(manager).post(f"/api/v1/sales/{self.sale['id']}/reverse/", {"reason": "Wrong size"}, format="json")
        self.assertEqual(reversed_.status_code, 200, reversed_.data)
        self.assertIn(b"VOID", client_for(self.cashier).get(self.url).content)

    def test_access_follows_sale_scope(self):
        printer = add_member(self.org, "printdesk", "cashier", sections=["printing"])
        self.assertEqual(client_for(printer).get(self.url).status_code, 404)  # other section's sale
        other_org, other_owner = make_org("Other", "other")
        self.assertEqual(client_for(other_owner).get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 403)  # signed out
