"""Private file storage for receipt photos and product images (T016).

* Files live in a private storage (settings.STORAGES["private"]), never under a
  public URL. Downloads go through the API, which checks permission and scope.
* Stored names are random (org/purpose/yyyy/mm/uuid.ext); the uploaded name is
  kept only as metadata.
* The type is decided from the file's own bytes, not its name or the browser's
  claim. Allowed: JPEG, PNG, WebP images and (for receipts) PDF.
* Images are re-encoded: resized to at most MAX_IMAGE_SIDE px and saved without
  metadata (no GPS location or camera details), which also neutralizes payloads
  hidden in image files and keeps files small on mobile data.
"""

import uuid
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.files.models import Attachment

MAX_UPLOAD_BYTES = getattr(settings, "MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 82


@dataclass(frozen=True)
class Purpose:
    code: str
    owner_type: str
    view_permission: str
    upload_permission: str
    delete_permission: str
    allow_pdf: bool
    max_per_owner: int
    replaces: bool = False  # a new upload replaces the existing one (single image)


PURPOSES = {
    "expense_receipt": Purpose(
        "expense_receipt", "expenses.expense", "expenses.view", "expenses.create", "expenses.manage", allow_pdf=True, max_per_owner=5
    ),
    "product_image": Purpose(
        "product_image",
        "catalog.product",
        "catalog.view",
        "catalog.manage",
        "catalog.manage",
        allow_pdf=False,
        max_per_owner=1,
        replaces=True,
    ),
}


def private_storage():
    return storages["private"]


def sniff(head):
    """File type from its first bytes."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _clean_image(data):
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs
    try:
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)  # keep phone photos the right way up
            has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = BytesIO()
            if has_alpha:
                image.convert("RGBA").save(out, "PNG", optimize=True)
                return out.getvalue(), "image/png", ".png", image.size
            image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            return out.getvalue(), "image/jpeg", ".jpg", image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ValidationError({"file": ["This image could not be read. Try taking the photo again."]}) from None


def prepare(upload, purpose):
    """Validate an uploaded file; return (bytes, content_type, extension)."""
    if upload is None:
        raise ValidationError({"file": ["Choose a file to upload."]})
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": [f"The file is too large. The limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."]})
    if upload.size == 0:
        raise ValidationError({"file": ["The file is empty."]})
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    kind = sniff(data[:16])
    if kind == "application/pdf":
        if not purpose.allow_pdf:
            raise ValidationError({"file": ["Upload a photo (JPEG, PNG or WebP)."]})
        return data, kind, ".pdf"
    if kind is None:
        allowed = "a photo (JPEG, PNG or WebP)" + (" or a PDF" if purpose.allow_pdf else "")
        raise ValidationError({"file": [f"This type of file is not accepted. Upload {allowed}."]})
    cleaned, content_type, extension, _size = _clean_image(data)
    return cleaned, content_type, extension


@transaction.atomic
def store(*, organization, purpose, owner, upload, actor, request=None):
    existing = Attachment.objects.filter(organization=organization, purpose=purpose.code, owner_id=owner.pk)
    if not purpose.replaces and existing.count() >= purpose.max_per_owner:
        raise ValidationError({"file": [f"This record already has {purpose.max_per_owner} files. Remove one first."]})
    data, content_type, extension = prepare(upload, purpose)
    now = timezone.now()
    key = f"{organization.pk}/{purpose.code}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
    saved_key = private_storage().save(key, ContentFile(data))
    replaced = []
    if purpose.replaces:
        for old in existing:
            replaced.append(old.storage_key)
            old.delete()
    attachment = Attachment.objects.create(
        organization=organization,
        storage_key=saved_key,
        original_name=(upload.name or "upload")[:255],
        content_type=content_type,
        file_size=len(data),
        purpose=purpose.code,
        owner_type=purpose.owner_type,
        owner_id=owner.pk,
        uploaded_by=actor,
    )
    # Remove replaced files only once the database change is committed.
    transaction.on_commit(lambda: [private_storage().delete(k) for k in replaced])
    record_event(
        organization=organization,
        action="file.uploaded",
        entity=attachment,
        actor=actor,
        request=request,
        summary={"purpose": purpose.code, "owner": str(owner.pk), "type": content_type, "size": len(data)},
    )
    return attachment


@transaction.atomic
def remove(attachment, *, actor, request=None):
    key = attachment.storage_key
    record_event(
        organization=attachment.organization,
        action="file.removed",
        entity=attachment,
        actor=actor,
        request=request,
        summary={"purpose": attachment.purpose, "owner": str(attachment.owner_id), "name": attachment.original_name},
    )
    attachment.delete()
    transaction.on_commit(lambda: private_storage().delete(key))
