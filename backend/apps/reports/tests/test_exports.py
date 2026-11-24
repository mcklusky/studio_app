from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.catalog.models import Customer, Product
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.reports.exports import safe_text

TODAY = timezone.localdate().isoformat()


class ExportTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        service = Product.objects.create(
            organization=self.org,
            section=self.clothing,
            name="Design fee",
            kind="service",
            tracks_stock=False,
            selling_price_base=Decimal("40.00"),
        )
        # A customer name crafted to run as a spreadsheet formula.
        self.customer = Customer.objects.create(organization=self.org, name='=HYPERLINK("http://evil.example","Click")')
        response = client_for(self.owner).post(
            "/api/v1/sales/",
            {
                "section": str(self.clothing.pk),
                "currency": "USD",
                "customer": str(self.customer.pk),
                "items": [{"product": str(service.pk), "quantity": "1"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="s1",
        )
        assert response.status_code == 201, response.data

    def export(self, report, file="xlsx", user=None, **params):
        return client_for(user or self.owner).get(f"/api/v1/reports/{report}/export/", {"file": file, "from": TODAY, "to": TODAY, **params})

    def workbook_text(self, response):
        sheet = load_workbook(BytesIO(response.content)).active
        return [[cell.value for cell in row] for row in sheet.iter_rows()]

    def test_xlsx_reflects_filters_and_figures(self):
        response = self.export("summary", section=str(self.clothing.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn(f"just-smile-summary-{TODAY}-to-{TODAY}.xlsx", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        rows = self.workbook_text(response)
        flat = [v for row in rows for v in row if v is not None]
        self.assertIn("Clothing", flat)  # section filter is stated
        self.assertIn("Generated", flat)  # generation date is stated
        revenue = next(row for row in rows if row[0] == "Revenue")
        self.assertEqual(Decimal(str(revenue[1])), Decimal("40.00"))

    def test_formula_like_text_is_neutralized(self):
        rows = self.workbook_text(self.export("customers"))
        names = [row[1] for row in rows if row[0] == 1]
        self.assertEqual(names, ["'" + self.customer.name])
        sheet = load_workbook(BytesIO(self.export("debts").content)).active
        self.assertFalse(any(cell.data_type == "f" for row in sheet.iter_rows() for cell in row))
        self.assertEqual(safe_text("+1 231"), "'+1 231")
        self.assertEqual(safe_text("Amara"), "Amara")

    def test_pdf_export(self):
        for report in ("summary", "products", "customers", "debts", "stock"):
            response = self.export(report, file="pdf")
            self.assertEqual(response.status_code, 200, report)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"))

    def test_access_and_audit(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.assertEqual(self.export("summary", user=cashier).status_code, 403)
        self.assertEqual(self.export("summary", user=printer).status_code, 403)
        self.assertEqual(self.export("summary", file="csv").status_code, 400)
        manager = add_member(self.org, "manager", "manager", sections=["printing"])
        foreign = self.export("summary", user=manager, section=str(self.clothing.pk))
        self.assertEqual(foreign.status_code, 400)
        self.export("products", file="pdf")
        event = AuditEvent.objects.get(action="report.exported")
        self.assertEqual((event.summary["report"], event.summary["format"]), ("products", "pdf"))
