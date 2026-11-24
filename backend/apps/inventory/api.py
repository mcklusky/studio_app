from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import ProductVariant
from apps.common.idempotency import run_idempotent
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, has_permission
from apps.inventory.models import StockAdjustment, StockMovement
from apps.inventory.services import VALUATION_BASIS, adjust_stock, stock_status
from apps.organizations.models import Branch

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=20, decimal_places=4))


def variant_label(variant):
    options = " / ".join(part for part in (variant.size, variant.color) if part)
    if variant.code == "default" and not options:
        return variant.product.name
    return f"{variant.product.name} · {options or variant.code}"


def can_see_costs(request):
    return has_permission(request.membership, "inventory.costs")


def selected_branch_ids(request):
    """Allowed branches, optionally narrowed to ?branch=<id> (which must be allowed)."""
    allowed = allowed_branch_ids(request.membership)
    wanted = request.query_params.get("branch")
    if not wanted:
        return allowed
    matches = [b for b in allowed if str(b) == wanted]
    if not matches:
        raise ValidationError({"branch": ["Choose a branch you have access to."]})
    return matches


class InventoryViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    action_permissions = {}

    def get_required_permission(self, _request):
        return self.action_permissions.get(getattr(self, "action", None))


class StockLevelViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, InventoryViewSet):
    """On-hand stock per variant (summed over the selected branches)."""

    action_permissions = {"list": "inventory.view", "retrieve": "inventory.view"}
    filter_backends = [SearchFilter]
    search_fields = ("product__name", "product__sku", "code", "size", "color")

    def get_queryset(self):
        membership = self.request.membership
        branches = selected_branch_ids(self.request)
        in_branches = Q(stock_balances__branch_id__in=branches)
        queryset = (
            ProductVariant.objects.filter(
                product__organization_id=membership.organization_id,
                product__section_id__in=allowed_section_ids(membership),
                product__tracks_stock=True,
            )
            .select_related("product", "product__section", "product__category")
            .annotate(
                on_hand=Coalesce(Sum("stock_balances__quantity", filter=in_branches), ZERO),
                stock_value=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("stock_balances__quantity") * F("stock_balances__average_cost_base"),
                            output_field=DecimalField(max_digits=24, decimal_places=7),
                        ),
                        filter=in_branches,
                    ),
                    ZERO,
                ),
            )
            .order_by("product__name", "code")
        )
        params = self.request.query_params
        if params.get("section"):
            queryset = queryset.filter(product__section_id=params["section"])
        if params.get("product"):
            queryset = queryset.filter(product_id=params["product"])
        if params.get("active", "true") == "true":
            queryset = queryset.filter(active=True, product__status="active")
        status = params.get("status")
        if status == "out":
            queryset = queryset.filter(on_hand__lte=0)
        elif status == "low":
            queryset = queryset.filter(on_hand__gt=0, on_hand__lte=F("product__minimum_stock"))
        elif status == "attention":
            queryset = queryset.filter(on_hand__lte=F("product__minimum_stock"))
        elif status:
            raise ValidationError({"status": ["Use out, low or attention."]})
        return queryset

    def serialize(self, variant, show_costs):
        on_hand = variant.on_hand
        row = {
            "variant_id": str(variant.pk),
            "product_id": str(variant.product_id),
            "label": variant_label(variant),
            "product_name": variant.product.name,
            "sku": variant.product.sku,
            "size": variant.size,
            "color": variant.color,
            "section": {"id": str(variant.product.section_id), "name": variant.product.section.name},
            "category": variant.product.category.name if variant.product.category_id else None,
            "on_hand": f"{on_hand.normalize():f}",
            "minimum_stock": f"{variant.product.minimum_stock.normalize():f}",
            "status": stock_status(on_hand, variant.product.minimum_stock),
        }
        if show_costs:
            average = (variant.stock_value / on_hand) if on_hand > 0 else Decimal("0")
            row["average_cost_base"] = f"{average.quantize(Decimal('0.0001'))}"
            row["stock_value_base"] = f"{variant.stock_value.quantize(Decimal('0.01'))}"
        return row

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        show_costs = can_see_costs(request)
        page = self.paginate_queryset(queryset)
        response = self.get_paginated_response([self.serialize(v, show_costs) for v in page])
        response.data["valuation_basis"] = VALUATION_BASIS
        if show_costs:
            total = queryset.aggregate(total=Sum("stock_value"))["total"] or Decimal("0")
            response.data["total_value_base"] = f"{total.quantize(Decimal('0.01'))}"
        return response

    def retrieve(self, request, *args, **kwargs):
        return Response(self.serialize(self.get_object(), can_see_costs(request)))


class StockMovementSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "variant",
            "label",
            "branch",
            "branch_name",
            "movement_type",
            "movement_type_label",
            "quantity_delta",
            "quantity_after",
            "unit_cost_base",
            "average_cost_after",
            "source_type",
            "source_id",
            "reason",
            "created_by_name",
            "created_at",
        )

    def get_label(self, movement):
        return variant_label(movement.variant)

    def get_created_by_name(self, movement):
        return movement.created_by.get_full_name() or movement.created_by.get_username()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("show_costs"):
            data.pop("unit_cost_base")
            data.pop("average_cost_after")
        return data


class StockMovementViewSet(mixins.ListModelMixin, InventoryViewSet):
    action_permissions = {"list": "inventory.view"}
    serializer_class = StockMovementSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "show_costs": can_see_costs(self.request)}

    def get_queryset(self):
        membership = self.request.membership
        queryset = StockMovement.objects.filter(
            organization_id=membership.organization_id,
            variant__product__section_id__in=allowed_section_ids(membership),
            branch_id__in=selected_branch_ids(self.request),
        ).select_related("variant__product", "branch", "created_by")
        params = self.request.query_params
        for param, field in (("variant", "variant_id"), ("product", "variant__product_id"), ("type", "movement_type")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        return queryset


class StockAdjustmentSerializer(serializers.ModelSerializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.select_related("product"))
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    quantity_delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost_base = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True, min_value=Decimal("0"))
    label = serializers.SerializerMethodField()
    quantity_after = serializers.DecimalField(source="movement.quantity_after", max_digits=12, decimal_places=3, read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = StockAdjustment
        fields = (
            "id",
            "variant",
            "label",
            "branch",
            "reason",
            "reason_label",
            "note",
            "quantity_delta",
            "unit_cost_base",
            "quantity_after",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_label(self, adjustment):
        return variant_label(adjustment.variant)

    def validate_variant(self, variant):
        membership = self.context["request"].membership
        if variant.product.organization_id != membership.organization_id or variant.product.section_id not in allowed_section_ids(
            membership
        ):
            raise serializers.ValidationError("Choose a product you have access to.")
        return variant

    def validate(self, attrs):
        membership = self.context["request"].membership
        allowed = allowed_branch_ids(membership)
        branch = attrs.get("branch")
        if branch is None:
            if len(allowed) != 1:
                raise serializers.ValidationError({"branch": ["Choose a branch."]})
            attrs["branch"] = Branch.objects.get(pk=allowed[0])
        elif branch.pk not in allowed:
            raise serializers.ValidationError({"branch": ["Choose a branch you have access to."]})
        return attrs


class StockAdjustmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, InventoryViewSet):
    action_permissions = {"list": "inventory.view", "retrieve": "inventory.view", "create": "inventory.adjust"}
    serializer_class = StockAdjustmentSerializer

    def get_queryset(self):
        membership = self.request.membership
        return StockAdjustment.objects.filter(
            organization_id=membership.organization_id,
            variant__product__section_id__in=allowed_section_ids(membership),
            branch_id__in=allowed_branch_ids(membership),
        ).select_related("variant__product", "movement")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = request.membership.organization

        def handler():
            adjustment = adjust_stock(
                organization=organization,
                variant=data["variant"],
                branch=data["branch"],
                quantity_delta=data["quantity_delta"],
                reason=data["reason"],
                note=data.get("note", ""),
                unit_cost_base=data.get("unit_cost_base"),
                actor=request.user,
                request=request,
            )
            return Response(self.get_serializer(adjustment).data, status=201)

        return run_idempotent(request, organization=organization, scope="stock.adjust", handler=handler)
