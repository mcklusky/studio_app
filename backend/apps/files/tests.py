import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditEvent
from apps.catalog.models import Product
from apps.expenses.models import ExpenseCategory
from apps.files.models import Attachment
from apps.files.services import private_storage
from apps.identity.tests.factories import add_member, client_for, make_org

TEMP = tempfile.mkdtemp(prefix="private-media-test-")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "private": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": TEMP, "base_url": None}},
}


def photo(name="receipt.jpg", size=(3000, 2000), fmt="JPEG", gps=True):
    image = Image.new("RGB", size, (200, 180, 40))
    out = BytesIO()
    if gps and fmt == "JPEG":
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # camera make
        exif[0x8825] = {2: (6.0, 18.0, 0.0)}  # GPS latitude
        image.save(out, fmt, exif=exif)
    else:
        image.save(out, fmt)
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


@override_settings(STORAGES=STORAGES)
class AttachmentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP, ignore_errors=True)

    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.clothing = self.org.sections.get(code="clothing")
        rent = ExpenseCategory.objects.create(organization=self.org, name="Rent")
        response = client_for(self.owner).post(
            "/api/v1/expenses/",
            {
                "category": str(rent.pk),
                "section": str(self.clothing.pk),
                "expense_date": timezone.localdate().isoformat(),
                "description": "Fuel",
                "method": "cash",
                "amount": "10",
                "currency": "USD",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="e1",
        )
        self.expense = response.data
        self.product = Product.objects.create(organization=self.org, section=self.clothing, name="Tee", selling_price_base=Decimal("5"))

    def upload(self, file, purpose="expense_receipt", owner=None, user=None):
        return client_for(user or self.owner).post(
            "/api/v1/attachments/", {"purpose": purpose, "owner": owner or self.expense["id"], "file": file}, format="multipart"
        )

    def test_photo_is_resized_and_stripped_of_metadata(self):
        response = self.upload(photo())
        self.assertEqual(response.status_code, 201, response.data)
        attachment = Attachment.objects.get()
        self.assertEqual(attachment.content_type, "image/jpeg")
        self.assertTrue(attachment.storage_key.startswith(f"{self.org.pk}/expense_receipt/"))
        self.assertNotIn("receipt.jpg", attachment.storage_key)  # stored under a random name, not the upload's
        with private_storage().open(attachment.storage_key, "rb") as handle:
            stored = Image.open(BytesIO(handle.read()))
            self.assertLessEqual(max(stored.size), 1600)
            self.assertEqual(len(stored.getexif()), 0)  # no GPS / camera data
        download = client_for(self.owner).get(response.data["url"])
        self.assertEqual(
            (download.status_code, download["Content-Type"], download["X-Content-Type-Options"]), (200, "image/jpeg", "nosniff")
        )
        self.assertTrue(AuditEvent.objects.filter(action="file.uploaded").exists())

    def test_type_is_checked_from_content(self):
        fake = SimpleUploadedFile("receipt.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        self.assertIn("file", self.upload(fake).data["error"]["field_errors"])
        pdf = SimpleUploadedFile("receipt.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", content_type="application/pdf")
        self.assertEqual(self.upload(pdf).status_code, 201)
        self.assertEqual(self.upload(pdf, purpose="product_image", owner=str(self.product.pk)).status_code, 400)  # images only
        broken = SimpleUploadedFile("x.jpg", b"\xff\xd8\xff\xe0broken", content_type="image/jpeg")
        self.assertEqual(self.upload(broken).status_code, 400)

    def test_size_limit(self):
        from apps.files import services

        original = services.MAX_UPLOAD_BYTES
        services.MAX_UPLOAD_BYTES = 1000
        try:
            response = self.upload(photo(size=(400, 400), gps=False))
            self.assertIn("too large", response.data["error"]["field_errors"]["file"][0])
        finally:
            services.MAX_UPLOAD_BYTES = original

    def test_permissions_and_scope(self):
        cashier = add_member(self.org, "cashier", "cashier", all_sections=True)  # no expenses.view
        printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        manager = add_member(self.org, "manager", "manager", sections=["printing"])  # expenses, but not clothing
        uploaded = self.upload(photo(gps=False)).data
        self.assertEqual(client_for(cashier).get(uploaded["url"]).status_code, 403)
        self.assertEqual(client_for(manager).get(uploaded["url"]).status_code, 404)  # outside their section
        self.assertEqual(self.upload(photo(gps=False), user=printer).status_code, 403)
        other_org, other_owner = make_org("Other", "other")
        self.assertEqual(client_for(other_owner).get(uploaded["url"]).status_code, 404)
        self.assertEqual(client_for(other_owner).delete(f"/api/v1/attachments/{uploaded['id']}/").status_code, 404)

    def test_product_image_replaces_and_is_listed(self):
        self.upload(photo(gps=False), purpose="product_image", owner=str(self.product.pk))
        first_key = Attachment.objects.get(purpose="product_image").storage_key
        with self.captureOnCommitCallbacks(execute=True):
            second = self.upload(photo("tee.png", fmt="PNG"), purpose="product_image", owner=str(self.product.pk)).data
        self.assertEqual(Attachment.objects.filter(purpose="product_image").count(), 1)
        self.assertFalse(private_storage().exists(first_key))  # replaced file is gone
        rows = client_for(self.owner).get("/api/v1/products/").data["results"]
        self.assertEqual(rows[0]["image_url"], second["url"])

    def test_receipt_limit_list_and_remove(self):
        for _ in range(5):
            self.upload(photo(size=(200, 200), gps=False))
        self.assertEqual(self.upload(photo(size=(200, 200), gps=False)).status_code, 400)
        listed = client_for(self.owner).get("/api/v1/attachments/", {"purpose": "expense_receipt", "owner": self.expense["id"]}).data
        self.assertEqual(len(listed), 5)
        key = Attachment.objects.get(pk=listed[0]["id"]).storage_key
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(client_for(self.owner).delete(f"/api/v1/attachments/{listed[0]['id']}/").status_code, 204)
        self.assertFalse(private_storage().exists(key))
        self.assertTrue(AuditEvent.objects.filter(action="file.removed").exists())
