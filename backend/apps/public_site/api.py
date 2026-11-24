"""Public website API (`/api/public/v1/`) and the staff endpoints that manage it (`/api/v1/website/`).

Public views use no authentication at all (so no session or CSRF coupling with the staff app),
are rate limited per visitor, and return only allow-listed fields.
"""

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.files.models import Attachment
from apps.files.services import private_storage
from apps.identity.scope import has_permission, resolve_membership
from apps.orders.models import CustomOrder, OrderKind
from apps.public_site import services
from apps.public_site.models import WebsiteProfile, WebsiteRequest

PROFILE_FIELDS = ("enabled", "headline", "about", "phone", "whatsapp", "email", "address", "hours", "map_url")
PUBLIC_PROFILE_FIELDS = ("headline", "about", "phone", "whatsapp", "email", "address", "hours", "map_url")


class PublicView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"


def _public_cache(response, seconds=60):
    response["Cache-Control"] = f"public, max-age={seconds}"
    return response


class PublicSiteView(PublicView):
    def get(self, request):
        profile = services.site_profile()
        organization = profile.organization
        sections = organization.sections.filter(active=True, code__in=OrderKind.values).order_by("name")
        data = {
            "name": organization.name,
            **{field: getattr(profile, field) for field in PUBLIC_PROFILE_FIELDS},
            "departments": [{"code": s.code, "name": s.name} for s in sections],
            "request_kinds": [{"value": v, "label": label} for v, label in WebsiteRequest.Kind.choices],
            "form_token": services.form_token(),
        }
        response = Response(data)
        response["Cache-Control"] = "no-store"  # carries a fresh form token
        return response


class PublicCatalogView(PublicView):
    def get(self, request):
        organization = services.site_profile().organization
        rate = services.lrd_rate(organization)
        products = list(services.published_products(organization))
        images = set(
            Attachment.objects.filter(
                organization=organization, purpose="product_image", owner_id__in=[p.pk for p in products]
            ).values_list("owner_id", flat=True)
        )
        rows = [
            {
                "id": str(p.pk),
                "name": p.name,
                "kind": p.kind,
                "section": {"code": p.section.code, "name": p.section.name},
                "description": p.public_description,
                "price_usd": str(p.selling_price_base),
                "price_lrd": services.lrd_price(p.selling_price_base, rate),
                "image_url": f"/api/public/v1/catalog/{p.pk}/image/" if p.pk in images else None,
            }
            for p in products
        ]
        return _public_cache(Response({"results": rows}))


class PublicProductImageView(PublicView):
    def get(self, request, pk):
        organization = services.site_profile().organization
        product = services.published_products(organization).filter(pk=pk).first()
        attachment = (
            Attachment.objects.filter(organization=organization, purpose="product_image", owner_id=pk).order_by("-created_at").first()
            if product
            else None
        )
        if attachment is None or not attachment.content_type.startswith("image/"):
            raise NotFound("Image not found.")
        try:
            handle = private_storage().open(attachment.storage_key, "rb")
        except FileNotFoundError:
            raise NotFound("Image not found.") from None
        response = FileResponse(handle, content_type=attachment.content_type)
        response["Cache-Control"] = "public, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PublicRequestView(PublicView):
    throttle_scope = "public_request"

    def post(self, request):
        organization = services.site_profile().organization
        row = services.create_request(organization, request.data, request=request)
        return Response({"number": row.number}, status=201)


class PublicTrackView(PublicView):
    throttle_scope = "public_track"

    def post(self, request):
        organization = services.site_profile().organization
        return Response(services.track(organization, request.data.get("number"), request.data.get("phone")))


# ---- Staff side ----------------------------------------------------------------------------------------------


def _staff(request):
    membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
    if not has_permission(membership, "website.manage"):
        raise PermissionDenied("Your role cannot manage the website.")
    return membership


def _request_row(row):
    return {
        "id": str(row.pk),
        "number": row.number,
        "kind": row.kind,
        "kind_label": row.get_kind_display(),
        "section": str(row.section_id) if row.section_id else None,
        "name": row.name,
        "phone": row.phone,
        "email": row.email,
        "message": row.message,
        "preferred_date": row.preferred_date.isoformat() if row.preferred_date else None,
        "status": row.status,
        "status_label": row.get_status_display(),
        "decline_reason": row.decline_reason,
        "customer": str(row.customer_id) if row.customer_id else None,
        "order": str(row.order_id) if row.order_id else None,
        "order_number": row.order.number if row.order_id else None,
        "handled_by": (row.handled_by.get_full_name() or row.handled_by.get_username()) if row.handled_by_id else None,
        "handled_at": row.handled_at,
        "created_at": row.created_at,
    }


class WebsiteProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _staff(request)
        profile, _ = WebsiteProfile.objects.get_or_create(organization=membership.organization)
        return Response({field: getattr(profile, field) for field in PROFILE_FIELDS} | {"updated_at": profile.updated_at})

    def put(self, request):
        membership = _staff(request)
        profile, _ = WebsiteProfile.objects.get_or_create(organization=membership.organization)
        errors = {}
        for field in PROFILE_FIELDS:
            if field not in request.data:
                continue
            value = request.data[field]
            if field == "enabled":
                if not isinstance(value, bool):
                    errors[field] = ["Use true or false."]
                    continue
            else:
                if not isinstance(value, str):
                    errors[field] = ["Enter text."]
                    continue
                value = value.strip()
                limit = WebsiteProfile._meta.get_field(field).max_length
                if limit and len(value) > limit:
                    errors[field] = [f"Keep this under {limit} characters."]
                    continue
            setattr(profile, field, value)
        if profile.map_url and not profile.map_url.startswith(("https://", "http://")):
            errors["map_url"] = ["Paste a full link starting with https://"]
        if profile.email and "@" not in profile.email:
            errors["email"] = ["Enter a valid email address."]
        if errors:
            raise ValidationError(errors)
        profile.updated_by = request.user
        profile.save()
        record_event(organization=membership.organization, action="website.profile_updated", entity=profile, request=request)
        return self.get(request)


class WebsiteRequestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _staff(request)
        rows = WebsiteRequest.objects.filter(organization=membership.organization).select_related("order", "handled_by")
        status = request.query_params.get("status")
        if status in WebsiteRequest.Status.values:
            rows = rows.filter(status=status)
        counts = {
            s: WebsiteRequest.objects.filter(organization=membership.organization, status=s).count() for s in WebsiteRequest.Status.values
        }
        return Response({"counts": counts, "results": [_request_row(r) for r in rows[:200]]})


class WebsiteRequestActionView(APIView):
    """POST customer/ (find or add the customer), accept/ {order}, decline/ {reason}."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, action):
        membership = _staff(request)
        row = WebsiteRequest.objects.select_for_update().filter(organization=membership.organization, pk=pk).first()
        if row is None:
            raise NotFound("Request not found.")
        if action == "customer":
            customer = services.find_or_create_customer(row, request.user, request=request)
            return Response(
                {
                    "id": str(customer.pk),
                    "name": customer.name,
                    "phone": customer.phone,
                    "email": customer.email,
                    "notes": customer.notes,
                    "active": customer.active,
                }
            )
        if row.status != WebsiteRequest.Status.NEW:
            raise ValidationError({"status": [f"{row.number} has already been {row.get_status_display().lower()}."]})
        if action == "accept":
            order = CustomOrder.objects.filter(organization=membership.organization, pk=request.data.get("order")).first()
            if order is None:
                raise ValidationError({"order": ["Create the order first, then link it."]})
            row.status, row.order, row.customer = WebsiteRequest.Status.ACCEPTED, order, order.customer
        elif action == "decline":
            reason = str(request.data.get("reason") or "").strip()
            if not reason:
                raise ValidationError({"reason": ["Say why, so the team knows (the customer does not see this)."]})
            row.status, row.decline_reason = WebsiteRequest.Status.DECLINED, reason[:240]
        else:
            raise NotFound("Unknown action.")
        row.handled_by, row.handled_at = request.user, timezone.now()
        row.save()
        record_event(
            organization=membership.organization,
            action=f"website.request_{row.status}",
            entity=row,
            request=request,
            summary={"number": row.number, "order": row.order.number if row.order_id else None},
        )
        return Response(_request_row(row))
