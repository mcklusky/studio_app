import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import Customer
from apps.organizations.models import BusinessSection, Organization


class WebsiteProfile(models.Model):
    """What the public website says about the business. Nothing here is private."""

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="website")
    enabled = models.BooleanField(default=False, help_text="Show the public website.")
    headline = models.CharField(max_length=140, blank=True)
    about = models.TextField(max_length=1200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=240, blank=True)
    hours = models.CharField(max_length=240, blank=True)
    map_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")


class WebsiteRequest(models.Model):
    """A booking or quote request from the website. Staff accept it (by creating a real order) or decline it.

    A request never posts a sale, an order or a payment by itself.
    """

    class Kind(models.TextChoices):
        PHOTOGRAPHY = "photography", "Photography or video"
        PRINTING = "printing", "Printing"
        CLOTHING = "clothing", "Custom clothing"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="website_requests")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    section = models.ForeignKey(BusinessSection, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40)
    email = models.EmailField(blank=True)
    message = models.TextField(max_length=2000)
    preferred_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    decline_reason = models.CharField(max_length=240, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    order = models.ForeignKey("orders.CustomOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="uniq_website_request_number")]
        indexes = [models.Index(fields=["organization", "status"], name="webreq_org_status_idx")]
