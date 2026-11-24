"""Operational commands: opening catalog import and the integrity check used after restores."""

import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Product
from apps.identity.tests.factories import add_member, make_org
from apps.inventory.models import StockBalance
from apps.sales.models import Sale

TEMPLATE = Path(__file__).resolve().parents[3] / "docs" / "onboarding" / "catalog-template.csv"


def run(*args):
    out, err = StringIO(), StringIO()
    try:
        call_command(*args, stdout=out, stderr=err)
        code = 0
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def csv_file(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return handle.name


class ImportCatalogTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")

    def test_template_imports_with_opening_stock(self):
        code, out, err = run("import_catalog", "--file", str(TEMPLATE), "--user", "owner", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("Nothing was saved", out)
        self.assertEqual(Product.objects.count(), 0)
        code, out, err = run("import_catalog", "--file", str(TEMPLATE), "--user", "owner")
        self.assertEqual(code, 0, err)
        tee = Product.objects.get(name="Just Smile Tee")
        self.assertEqual(sorted(v.size for v in tee.variants.all()), ["L", "M"])
        self.assertEqual(StockBalance.objects.filter(variant__product=tee).count(), 2)
        cap = StockBalance.objects.get(variant__product__name="Plain cap")
        self.assertEqual((cap.quantity, cap.average_cost_base), (Decimal("10.000"), Decimal("2.5000")))  # cost from buying_price
        self.assertFalse(Product.objects.get(name="A4 colour print").tracks_stock)

    def test_all_or_nothing_with_line_numbers(self):
        path = csv_file(
            "section,name,selling_price,opening_quantity,opening_unit_cost\n"
            "Clothing,Good shirt,10,5,4\n"
            "Bakery,Bread,2,,\n"
            "Clothing,Free shirt,abc,,\n"
            "Clothing,Costless,5,3,\n"
        )
        code, _, err = run("import_catalog", "--file", path, "--user", "owner")
        self.assertEqual(code, 1)
        self.assertIn("line 3: unknown section", err)
        self.assertIn("line 4: selling_price 'abc' is not a number", err)
        self.assertIn("line 5: opening stock needs opening_unit_cost", err)
        self.assertEqual(Product.objects.count(), 0)

    def test_refuses_existing_products_and_unauthorized_user(self):
        run("import_catalog", "--file", str(TEMPLATE), "--user", "owner")
        code, _, err = run("import_catalog", "--file", str(TEMPLATE), "--user", "owner")
        self.assertEqual(code, 1)
        self.assertIn("already in the catalog", err)
        add_member(self.org, "cashier", "cashier", all_sections=True)
        with self.assertRaisesMessage(Exception, "allowed to adjust inventory"):
            call_command("import_catalog", "--file", str(TEMPLATE), "--user", "cashier", stdout=StringIO(), stderr=StringIO())


class VerifyIntegrityTests(TestCase):
    def test_passes_then_detects_tampering(self):
        org, owner = make_org("Studio", "owner")
        run("import_catalog", "--file", str(TEMPLATE), "--user", "owner")
        code, out, _ = run("verify_integrity")
        self.assertEqual(code, 0)
        self.assertIn("All checks passed", out)
        StockBalance.objects.filter(variant__product__name="Plain cap").update(quantity=Decimal("99"))
        code, _, err = run("verify_integrity")
        self.assertEqual(code, 1)
        self.assertIn("Plain cap: balance 99 but ledger 10", err)
        self.assertEqual(Sale.objects.count(), 0)
