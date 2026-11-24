"""Public website rules.

* Only one organization is shown: settings.PUBLIC_SITE_ORGANIZATION_ID, or else the only one with its website enabled.
* Public responses use allow-listed fields: never costs, balances of other people, staff names or customer lists.
* Order tracking needs the number AND the phone number on the record; any mismatch gives the same "not found".
"""

import re
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.audit.services import record_event
from apps.catalog.models import Customer, Product
from apps.common.numbering import next_number
from apps.currencies.services import current_rate
from apps.orders.models import STATUS_LABELS, CustomOrder, OrderKind
from apps.public_site.models import WebsiteProfile, WebsiteRequest
from apps.sales.models import Sale

FORM_SALT = "public-site.request-form"
FORM_MIN_SECONDS = 3  # faster than a person can fill the form: treat as a bot
FORM_MAX_SECONDS = 4 * 60 * 60
CENTS = Decimal("0.01")
NOT_FOUND = "We could not find an order with that number and phone number. Check both and try again."


def site_profile():
    """The enabled website, or 404 when none is set up."""
    rows = WebsiteProfile.objects.filter(enabled=True, organization__active=True).select_related("organization")
    wanted = getattr(settings, "PUBLIC_SITE_ORGANIZATION_ID", "")
    if wanted:
        rows = rows.filter(organization_id=wanted)
    profiles = list(rows[:2])
    if len(profiles) != 1:
        raise NotFound("The website is not available right now.")
    return profiles[0]


def form_token():
    return signing.TimestampSigner(salt=FORM_SALT).sign(str(int(timezone.now().timestamp())))


def check_form_token(token):
    """A signed issue time: rejects missing/forged tokens, instant bot submissions and very old forms."""
    try:
        issued = int(signing.TimestampSigner(salt=FORM_SALT).unsign(token or "", max_age=FORM_MAX_SECONDS))
    except (signing.BadSignature, ValueError):
        raise ValidationError({"form": ["This form has expired. Refresh the page and try again."]}) from None
    if timezone.now().timestamp() - issued < FORM_MIN_SECONDS:
        raise ValidationError({"form": ["Please take a moment to check your details, then send again."]})


def digits(value):
    return re.sub(r"\D", "", value or "")


def phones_match(entered, on_record):
    a, b = digits(entered), digits(on_record)
    return len(a) >= 7 and len(b) >= 7 and a[-7:] == b[-7:]


def published_products(organization):
    return (
        Product.objects.filter(organization=organization, show_online=True, status=Product.Status.ACTIVE, section__active=True)
        .select_related("section")
        .order_by("section__name", "name")
    )


def lrd_rate(organization):
    rate = current_rate(organization, "LRD", timezone.localdate())
    return rate.units_per_usd if rate else None


def lrd_price(usd, rate):
    return str((Decimal(usd) * rate).quantize(CENTS)) if rate else None


@transaction.atomic
def create_request(organization, data, request=None):
    if data.get("website"):  # honeypot field hidden from people
        raise ValidationError({"form": ["Your request could not be sent."]})
    check_form_token(data.get("token"))
    errors = {}
    name = str(data.get("name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    message = str(data.get("message") or "").strip()
    kind = data.get("kind") or ""
    if not name:
        errors["name"] = ["Tell us your name."]
    if len(digits(phone)) < 7:
        errors["phone"] = ["Enter a phone number we can call or WhatsApp."]
    if len(message) < 5:
        errors["message"] = ["Tell us a little about what you need."]
    if kind not in WebsiteRequest.Kind.values:
        errors["kind"] = ["Choose what you need."]
    preferred = None
    if data.get("preferred_date"):
        try:
            preferred = timezone.datetime.fromisoformat(str(data["preferred_date"])).date()
        except ValueError:
            errors["preferred_date"] = ["Enter a valid date."]
        else:
            if preferred < timezone.localdate():
                errors["preferred_date"] = ["Choose today or a later date."]
    email = str(data.get("email") or "").strip()
    if email and ("@" not in email or len(email) > 254):
        errors["email"] = ["Enter a valid email address, or leave it blank."]
    if errors:
        raise ValidationError(errors)
    section = organization.sections.filter(code=kind, active=True).first() if kind in OrderKind.values else None
    row = WebsiteRequest.objects.create(
        organization=organization,
        number=next_number(organization, "REQ"),
        kind=kind,
        section=section,
        name=name[:120],
        phone=phone[:40],
        email=email,
        message=message[:2000],
        preferred_date=preferred,
    )
    record_event(organization=organization, action="website.request_received", entity=row, summary={"number": row.number, "kind": kind})
    return row


def track(organization, number, phone):
    """Status of one order or sale, only when the phone number matches the customer on it."""
    number = str(number or "").strip().upper()
    if not number or not phone:
        raise NotFound(NOT_FOUND)
    order = CustomOrder.objects.filter(organization=organization, number=number).select_related("customer").first()
    if order and phones_match(phone, order.customer.phone):
        flow = order.flow
        current = flow.index(order.status) if order.status in flow else -1
        return {
            "type": "order",
            "number": order.number,
            "title": order.title,
            "kind": order.get_kind_display(),
            "status": order.status,
            "status_label": order.status_label,
            "cancelled": order.status == "cancelled",
            "steps": [{"label": STATUS_LABELS[s], "done": i <= current, "current": i == current} for i, s in enumerate(flow)],
            "due_date": order.due_date.isoformat(),
            "currency": order.currency,
            "total": str(order.total),
            "paid": str(order.paid_amount),
            "balance_due": str(order.balance_due),
        }
    sale = Sale.objects.filter(organization=organization, number=number).select_related("customer").first()
    if sale and sale.customer_id and phones_match(phone, sale.customer.phone):
        return {
            "type": "sale",
            "number": sale.number,
            "title": "Purchase",
            "kind": "Receipt",
            "status": sale.status,
            "status_label": "Reversed" if sale.status == Sale.Status.REVERSED else ("Paid" if sale.balance_due <= 0 else "Balance due"),
            "cancelled": sale.status == Sale.Status.REVERSED,
            "steps": [],
            "due_date": None,
            "currency": sale.currency,
            "total": str(sale.total),
            "paid": str(sale.paid_amount),
            "balance_due": str(sale.balance_due),
        }
    raise NotFound(NOT_FOUND)


def find_or_create_customer(website_request, actor, request=None):
    """Match the requester to an existing customer by phone, or add them, so staff can create the order."""
    if website_request.customer_id:
        return website_request.customer
    organization = website_request.organization
    wanted = digits(website_request.phone)[-7:]
    match = None
    if wanted:
        for customer in Customer.objects.filter(organization=organization, active=True).exclude(phone=""):
            if digits(customer.phone)[-7:] == wanted:
                match = customer
                break
    if match is None:
        match = Customer.objects.create(
            organization=organization,
            name=website_request.name,
            phone=website_request.phone,
            email=website_request.email,
            notes=f"Added from website request {website_request.number}.",
        )
        record_event(
            organization=organization, action="customer.created", entity=match, actor=actor, request=request, summary={"source": "website"}
        )
    website_request.customer = match
    website_request.save(update_fields=["customer"])
    return match
