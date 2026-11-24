from decimal import Decimal

from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import ProductVariant, Supplier
from apps.common.filters import date_param
from apps.common.idempotency import run_idempotent
from apps.currencies.models import Currency
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_branch_ids, allowed_section_ids
from apps.inventory.api import variant_label
from apps.organizations.models import Branch, BusinessSection
from apps.purchasing import services
from apps.purchasing.models import GoodsReceipt, Purchase

POSITIVE = Decimal("0")


class LineInputSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.select_related("product"))
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PurchaseInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    section = serializers.PrimaryKeyRelatedField(queryset=BusinessSection.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    purchase_date = serializers.DateField()
    currency = serializers.ChoiceField(choices=Currency.choices)
    supplier_reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    shipping_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=POSITIVE)
    other_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=POSITIVE)
    lines = LineInputSerializer(many=True)

    def validate_purchase_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Purchase date cannot be in the future.")
        return value

    def validate(self, attrs):
        membership = self.context["request"].membership
        org_id = membership.organization_id
        supplier, section = attrs.get("supplier"), attrs.get("section")
        if supplier is not None and supplier.organization_id != org_id:
            raise serializers.ValidationError({"supplier": ["Choose a supplier in this organization."]})
        if section is not None and (section.organization_id != org_id or section.pk not in allowed_section_ids(membership)):
            raise serializers.ValidationError({"section": ["Choose a section you have access to."]})
        allowed_branches = allowed_branch_ids(membership)
        branch = attrs.get("branch")
        if branch is None and not self.partial:
            if len(allowed_branches) != 1:
                raise serializers.ValidationError({"branch": ["Choose a branch."]})
            attrs["branch"] = Branch.objects.get(pk=allowed_branches[0])
        elif branch is not None and branch.pk not in allowed_branches:
            raise serializers.ValidationError({"branch": ["Choose a branch you have access to."]})
        for index, line in enumerate(attrs.get("lines") or []):
            if line["variant"].product.organization_id != org_id:
                raise serializers.ValidationError({f"lines.{index}.variant": ["Choose an item in this organization."]})
        return attrs


class PurchaseLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    variant = serializers.UUIDField(source="variant_id")
    label = serializers.SerializerMethodField()
    tracks_stock = serializers.BooleanField(source="variant.product.tracks_stock")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    quantity_received = serializers.DecimalField(max_digits=12, decimal_places=3)
    quantity_outstanding = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2)

    def get_label(self, line):
        return variant_label(line.variant)


class ReceiptSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    reversed_by_name = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = (
            "id",
            "number",
            "received_date",
            "note",
            "created_by_name",
            "created_at",
            "reversed_at",
            "reversed_by_name",
            "reversal_reason",
            "lines",
        )

    def get_created_by_name(self, receipt):
        return receipt.created_by.get_full_name() or receipt.created_by.get_username()

    def get_reversed_by_name(self, receipt):
        user = receipt.reversed_by
        return (user.get_full_name() or user.get_username()) if user else None

    def get_lines(self, receipt):
        return [
            {
                "purchase_line": str(line.purchase_line_id),
                "label": variant_label(line.purchase_line.variant),
                "quantity": str(line.quantity),
                "landed_unit_cost": str(line.landed_unit_cost),
            }
            for line in receipt.lines.all()
        ]


class PurchaseSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name")
    section_name = serializers.CharField(source="section.name")
    status_label = serializers.CharField(source="get_status_display")
    created_by_name = serializers.SerializerMethodField()
    line_count = serializers.SerializerMethodField()
    balance_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Purchase
        fields = (
            "id",
            "number",
            "supplier",
            "supplier_name",
            "section",
            "section_name",
            "branch",
            "purchase_date",
            "supplier_reference",
            "status",
            "status_label",
            "currency",
            "fx_units_per_usd",
            "fx_rate_to_base",
            "fx_rate_date",
            "shipping_cost",
            "other_cost",
            "subtotal",
            "total",
            "base_total",
            "paid_amount",
            "balance_due",
            "notes",
            "cancel_reason",
            "created_by_name",
            "line_count",
            "created_at",
            "updated_at",
        )

    def get_created_by_name(self, purchase):
        return purchase.created_by.get_full_name() or purchase.created_by.get_username()

    def get_line_count(self, purchase):
        return len(purchase.lines.all())


class PurchaseDetailSerializer(PurchaseSerializer):
    lines = PurchaseLineSerializer(many=True)
    receipts = ReceiptSerializer(many=True)

    class Meta(PurchaseSerializer.Meta):
        fields = PurchaseSerializer.Meta.fields + ("lines", "receipts")


class PurchaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    filter_backends = [SearchFilter]
    search_fields = ("number", "supplier__name", "supplier_reference")
    PERMISSIONS = {
        "list": "purchases.view",
        "retrieve": "purchases.view",
        "create": "purchases.create",
        "partial_update": "purchases.create",
        "receive": "purchases.receive",
        "reverse_receipt": "purchases.receive",
        "cancel": "purchases.create",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_serializer_class(self):
        return PurchaseSerializer if self.action == "list" else PurchaseDetailSerializer

    def get_queryset(self):
        membership = self.request.membership
        queryset = (
            Purchase.objects.filter(
                organization_id=membership.organization_id,
                section_id__in=allowed_section_ids(membership),
                branch_id__in=allowed_branch_ids(membership),
            )
            .select_related("supplier", "section", "created_by")
            .prefetch_related(
                "lines__variant__product",
                "receipts__lines__purchase_line__variant__product",
                "receipts__created_by",
                "receipts__reversed_by",
            )
        )
        params = self.request.query_params
        for param, field in (("status", "status"), ("supplier", "supplier_id"), ("section", "section_id")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        start, end = date_param(self.request, "from"), date_param(self.request, "to")
        if start:
            queryset = queryset.filter(purchase_date__gte=start)
        if end:
            queryset = queryset.filter(purchase_date__lte=end)
        return queryset

    def _detail(self, purchase, status=200):
        purchase = self.get_queryset().get(pk=purchase.pk)
        return Response(PurchaseDetailSerializer(purchase, context=self.get_serializer_context()).data, status=status)

    def create(self, request):
        data = self._validated(PurchaseInputSerializer(data=request.data, context={"request": request}))
        organization = request.membership.organization

        def handler():
            purchase = services.create_purchase(organization=organization, actor=request.user, request=request, **data)
            return self._detail(purchase, status=201)

        return run_idempotent(request, organization=organization, scope="purchases.create", handler=handler)

    def partial_update(self, request, pk=None):
        purchase = self.get_object()
        data = self._validated(PurchaseInputSerializer(data=request.data, partial=True, context={"request": request}))
        if "section" in data and data["section"].pk != purchase.section_id:
            raise ValidationError({"section": ["Create a new purchase to change section."]})
        data.pop("section", None)
        data.pop("branch", None)
        purchase = services.update_purchase(purchase, actor=request.user, request=request, **data)
        return self._detail(purchase)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        purchase = self.get_object()
        lines = request.data.get("lines")
        if not isinstance(lines, dict):
            raise ValidationError({"lines": ["Send quantities as {purchase_line_id: quantity}."]})
        try:
            quantities = {str(key): Decimal(str(value or "0")) for key, value in lines.items()}
        except Exception as exc:
            raise ValidationError({"lines": ["Quantities must be numbers."]}) from exc
        received_date = request.data.get("received_date")
        note = str(request.data.get("note", ""))[:240]

        def handler():
            services.receive_goods(
                purchase,
                actor=request.user,
                request=request,
                quantities=quantities,
                note=note,
                received_date=serializers.DateField().to_internal_value(received_date) if received_date else None,
            )
            return self._detail(purchase, status=201)

        return run_idempotent(request, organization=purchase.organization, scope="purchases.receive", handler=handler, required=True)

    @action(detail=True, methods=["post"], url_path=r"receipts/(?P<receipt_id>[0-9a-f-]+)/reverse")
    def reverse_receipt(self, request, pk=None, receipt_id=None):
        purchase = self.get_object()
        receipt = purchase.receipts.filter(pk=receipt_id).first()
        if receipt is None:
            raise NotFound()
        services.reverse_receipt(receipt, actor=request.user, reason=str(request.data.get("reason", "")), request=request)
        return self._detail(purchase)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase = self.get_object()
        services.cancel_purchase(purchase, actor=request.user, reason=str(request.data.get("reason", "")), request=request)
        return self._detail(purchase)

    @staticmethod
    def _validated(serializer):
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)
