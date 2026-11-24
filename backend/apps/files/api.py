"""Attachment upload, list, download and removal. Every request is checked against the
owning record: permission for its purpose and the caller's section/branch scope."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.expenses.models import Expense
from apps.files import services
from apps.files.models import Attachment
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, has_permission, resolve_membership


def _owner(purpose, membership, owner_id):
    """The record the file belongs to, if it exists in the caller's scope."""
    sections = allowed_section_ids(membership)
    try:
        if purpose.code == "expense_receipt":
            return Expense.objects.get(
                pk=owner_id,
                organization_id=membership.organization_id,
                section_id__in=sections,
                branch_id__in=allowed_branch_ids(membership),
            )
        return Product.objects.get(pk=owner_id, organization_id=membership.organization_id, section_id__in=sections)
    except (Expense.DoesNotExist, Product.DoesNotExist, ValueError, DjangoValidationError):
        raise NotFound("That record was not found.") from None


def _purpose(code):
    purpose = services.PURPOSES.get(code or "")
    if purpose is None:
        raise ValidationError({"purpose": [f"Use one of: {', '.join(services.PURPOSES)}."]})
    return purpose


def _require(membership, code):
    if not has_permission(membership, code):
        raise PermissionDenied("You do not have permission to perform this action.")


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ("id", "purpose", "owner_id", "original_name", "content_type", "file_size", "url", "uploaded_by_name", "created_at")

    def get_url(self, attachment):
        return f"/api/v1/attachments/{attachment.pk}/file/"

    def get_uploaded_by_name(self, attachment):
        return attachment.uploaded_by.get_full_name() or attachment.uploaded_by.get_username()


class AttachmentListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        purpose = _purpose(request.query_params.get("purpose"))
        _require(membership, purpose.view_permission)
        owner = _owner(purpose, membership, request.query_params.get("owner"))
        rows = Attachment.objects.filter(organization_id=membership.organization_id, purpose=purpose.code, owner_id=owner.pk)
        return Response(AttachmentSerializer(rows.select_related("uploaded_by"), many=True).data)

    def post(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        purpose = _purpose(request.data.get("purpose"))
        _require(membership, purpose.upload_permission)
        owner = _owner(purpose, membership, request.data.get("owner"))
        attachment = services.store(
            organization=membership.organization,
            purpose=purpose,
            owner=owner,
            upload=request.FILES.get("file"),
            actor=request.user,
            request=request,
        )
        return Response(AttachmentSerializer(attachment).data, status=201)


class AttachmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _load(self, request, pk, permission_attr):
        attachment = Attachment.objects.select_related("organization", "uploaded_by").filter(pk=pk).first()
        if attachment is None:
            raise NotFound("File not found.")
        try:
            # <img> tags cannot send the organization header, so resolve against the file's own organization.
            membership = resolve_membership(request.user, str(attachment.organization_id))
        except NotFound:
            raise NotFound("File not found.") from None
        purpose = _purpose(attachment.purpose)
        _require(membership, getattr(purpose, permission_attr))
        _owner(purpose, membership, attachment.owner_id)
        return attachment

    def delete(self, request, pk):
        attachment = self._load(request, pk, "delete_permission")
        services.remove(attachment, actor=request.user, request=request)
        return Response(status=204)


class AttachmentFileView(AttachmentDetailView):
    def get(self, request, pk):
        attachment = self._load(request, pk, "view_permission")
        try:
            handle = services.private_storage().open(attachment.storage_key, "rb")
        except FileNotFoundError:
            raise NotFound("The stored file is missing. Ask an administrator to check backups.") from None
        inline = attachment.content_type.startswith("image/") or request.query_params.get("inline") == "1"
        extension = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(attachment.content_type, "bin")
        response = FileResponse(
            handle,
            content_type=attachment.content_type,
            as_attachment=not inline,
            filename=f"{attachment.purpose}-{str(attachment.pk)[:8]}.{extension}",
        )
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
        return response
