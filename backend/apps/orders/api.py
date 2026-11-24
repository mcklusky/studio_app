from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Customer, Product, ProductVariant
from apps.common.idempotency import run_idempotent
from apps.currencies.models import Currency
from apps.identity.models import Membership
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, has_permission
from apps.inventory.api import variant_label
from apps.orders import services
from apps.orders.models import CLOSED_STATUSES, STATUS_LABELS, CustomOrder, OrderKind, OrderMaterial
from apps.organizations.models import Branch, BusinessSection
from apps.payments.services import pay_order
from apps.sales.api import PaymentInputSerializer, person

MONEY = {"max_digits": 14, "decimal_places": 2}
DUE_SOON_DAYS = 3


# ---------- input ----------


class PhotographyInput(serializers.Serializer):
    shoot_type = serializers.CharField(max_length=80)
    package = serializers.CharField(max_length=80, required=False, allow_blank=True)
    shoot_at = serializers.DateTimeField()
    location = serializers.CharField(max_length=160, required=False, allow_blank=True)
    photos_promised = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class PrintingInput(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    item = serializers.CharField(max_length=120)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    size = serializers.CharField(max_length=60, required=False, allow_blank=True)
    material = serializers.CharField(max_length=80, required=False, allow_blank=True)
    design = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ClothingInput(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    item = serializers.CharField(max_length=120)
    color = serializers.CharField(max_length=60, required=False, allow_blank=True)
    design = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ClothingItemInput(serializers.Serializer):
    size = serializers.CharField(max_length=20)
    custom_name = serializers.CharField(max_length=40, required=False, allow_blank=True)
    custom_number = serializers.CharField(max_length=10, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)


DETAIL_INPUTS = {OrderKind.PHOTOGRAPHY: PhotographyInput, OrderKind.PRINTING: PrintingInput, OrderKind.CLOTHING: ClothingInput}


class OrderInput(serializers.Serializer):
    section = serializers.PrimaryKeyRelatedField(queryset=BusinessSection.objects.all(), required=False)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)
    currency = serializers.ChoiceField(choices=Currency.choices, required=False)
    total = serializers.DecimalField(**MONEY, min_value=Decimal("0"), required=False)
    production_cost = serializers.DecimalField(**MONEY, min_value=Decimal("0"), required=False, allow_null=True)
    due_date = serializers.DateField(required=False)
    title = serializers.CharField(max_length=160, required=False, allow_blank=True)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all(), required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    detail = serializers.DictField(required=False)
    items = ClothingItemInput(many=True, required=False)
    deposit = PaymentInputSerializer(required=False, allow_null=True)

    CREATE_REQUIRED = ("section", "customer", "currency", "total", "due_date", "detail")

    def validate(self, attrs):
        membership = self.context["request"].membership
        order = self.context.get("order")
        org_id = membership.organization_id
        if order is None:
            missing = {f: ["This field is required."] for f in self.CREATE_REQUIRED if attrs.get(f) in (None, "")}
            if missing:
                raise ValidationError(missing)
            section = attrs["section"]
            if section.organization_id != org_id or section.pk not in allowed_section_ids(membership):
                raise ValidationError({"section": ["Choose a section you have access to."]})
            kind = services.kind_for_section(section)
            allowed_branches = allowed_branch_ids(membership)
            branch = attrs.get("branch")
            if branch is None:
                if len(allowed_branches) != 1:
                    raise ValidationError({"branch": ["Choose a branch."]})
                attrs["branch"] = Branch.objects.get(pk=allowed_branches[0])
            elif branch.pk not in allowed_branches:
                raise ValidationError({"branch": ["Choose a branch you have access to."]})
            if attrs["due_date"] < timezone.localdate():
                raise ValidationError({"due_date": ["The due date cannot be in the past."]})
        else:
            for frozen in ("section", "branch", "currency", "deposit"):
                if frozen in attrs:
                    raise ValidationError({frozen: ["This cannot be changed after the order is created."]})
            section, kind = order.section, order.kind
        customer = attrs.get("customer")
        if customer is not None and (customer.organization_id != org_id or not customer.active):
            raise ValidationError({"customer": ["Choose an active customer."]})
        assignee = attrs.get("assigned_to")
        if assignee is not None and assignee.pk not in {s["id"] for s in eligible_staff(membership.organization, section)}:
            raise ValidationError({"assigned_to": ["Choose a staff member who works in this section."]})

        if "detail" in attrs:
            detail = DETAIL_INPUTS[kind](data=attrs["detail"])
            if not detail.is_valid():
                raise ValidationError({f"detail.{k}": v for k, v in detail.errors.items()})
            attrs["detail"] = dict(detail.validated_data)
            product = attrs["detail"].get("product")
            if product is not None and product.organization_id != org_id:
                raise ValidationError({"detail.product": ["Choose a product from your catalog."]})
        if kind == OrderKind.CLOTHING:
            if order is None and not attrs.get("items"):
                raise ValidationError({"items": ["Add at least one size line."]})
            if "items" in attrs and not attrs["items"]:
                raise ValidationError({"items": ["Add at least one size line."]})
        elif attrs.get("items"):
            raise ValidationError({"items": ["Size lines only apply to clothing orders."]})
        attrs["kind"] = kind
        return attrs


def default_title(kind, detail, items):
    if kind == OrderKind.PHOTOGRAPHY:
        return " · ".join(filter(None, [detail.get("shoot_type"), detail.get("package")]))
    if kind == OrderKind.PRINTING:
        return f"{detail.get('item')} × {Decimal(detail.get('quantity', 1)).normalize():f}"
    return f"{detail.get('item')} × {sum(i.get('quantity', 1) for i in items or [])}"


def eligible_staff(organization, section):
    """Active members who can work orders in this section."""
    memberships = (
        Membership.objects.filter(organization=organization, active=True, role__permissions__code="orders.update")
        .filter(Q(all_sections=True) | Q(sections=section))
        .select_related("user")
        .distinct()
    )
    return sorted(({"id": m.user_id, "name": person(m.user)} for m in memberships if m.user.is_active), key=lambda s: s["name"].lower())


# ---------- output ----------


def is_overdue(order, today=None):
    return order.is_open and order.due_date < (today or timezone.localdate())


class OrderSummarySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name")
    customer_phone = serializers.CharField(source="customer.phone")
    section_name = serializers.CharField(source="section.name")
    kind_label = serializers.CharField(source="get_kind_display")
    status_label = serializers.CharField()
    balance_due = serializers.DecimalField(**MONEY)
    assigned_to_name = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    step = serializers.SerializerMethodField()
    shoot_at = serializers.SerializerMethodField()

    class Meta:
        model = CustomOrder
        fields = (
            "id",
            "number",
            "kind",
            "kind_label",
            "section",
            "section_name",
            "customer",
            "customer_name",
            "customer_phone",
            "title",
            "status",
            "status_label",
            "step",
            "currency",
            "fx_units_per_usd",
            "total",
            "base_total",
            "paid_amount",
            "balance_due",
            "due_date",
            "overdue",
            "shoot_at",
            "assigned_to",
            "assigned_to_name",
            "created_at",
            "delivered_at",
        )

    def get_assigned_to_name(self, order):
        return person(order.assigned_to)

    def get_overdue(self, order):
        return is_overdue(order)

    def get_step(self, order):
        flow = order.flow
        index = flow.index(order.status) if order.status in flow else None
        following = flow[index + 1] if index is not None and index + 1 < len(flow) and order.status not in CLOSED_STATUSES else None
        return {
            "index": index + 1 if index is not None else None,
            "count": len(flow),
            "next": {"code": following, "label": STATUS_LABELS[following]} if following else None,
        }

    def get_shoot_at(self, order):
        detail = getattr(order, "photography", None) if order.kind == OrderKind.PHOTOGRAPHY else None
        return detail.shoot_at.isoformat() if detail else None


class OrderDetailSerializer(OrderSummarySerializer):
    detail = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    materials = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    flow = serializers.SerializerMethodField()

    class Meta(OrderSummarySerializer.Meta):
        fields = OrderSummarySerializer.Meta.fields + (
            "branch",
            "production_cost",
            "notes",
            "fx_rate_date",
            "created_by_name",
            "cancelled_at",
            "cancel_reason",
            "detail",
            "items",
            "history",
            "payments",
            "materials",
            "flow",
        )

    def get_created_by_name(self, order):
        return person(order.created_by)

    def get_flow(self, order):
        return [{"code": s, "label": STATUS_LABELS[s]} for s in order.flow]

    def get_detail(self, order):
        detail = getattr(order, order.kind, None)
        if detail is None:
            return {}
        fields = {
            OrderKind.PHOTOGRAPHY: ("shoot_type", "package", "shoot_at", "location", "photos_promised"),
            OrderKind.PRINTING: ("product", "item", "quantity", "size", "material", "design"),
            OrderKind.CLOTHING: ("product", "item", "color", "design"),
        }[order.kind]
        data = {}
        for field in fields:
            value = getattr(detail, f"{field}_id" if field == "product" else field)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif value is not None and not isinstance(value, (int, str)):
                value = f"{value.normalize():f}" if isinstance(value, Decimal) else str(value)
            data[field] = value
        if "product" in data:
            data["product_name"] = detail.product.name if detail.product_id else None
        return data

    def get_items(self, order):
        return [
            {"size": i.size, "custom_name": i.custom_name, "custom_number": i.custom_number, "quantity": i.quantity}
            for i in order.clothing_items.all()
        ]

    def get_history(self, order):
        return [
            {
                "from": e.from_status,
                "to": e.to_status,
                "to_label": STATUS_LABELS.get(e.to_status, e.to_status),
                "note": e.note,
                "correction": e.is_correction,
                "actor": person(e.actor),
                "at": e.created_at.isoformat(),
            }
            for e in order.status_events.all()
        ]

    def get_payments(self, order):
        return [
            {
                "id": str(a.payment_id),
                "number": a.payment.number,
                "status": a.payment.status,
                "method_label": a.payment.get_method_display(),
                "reference": a.payment.reference,
                "amount": str(a.amount),
                "received_at": a.payment.received_at.isoformat(),
                "created_by_name": person(a.payment.created_by),
                "reversal_reason": a.payment.reversal_reason,
            }
            for a in order.allocations.all()
        ]

    def get_materials(self, order):
        return [
            {
                "id": str(m.id),
                "variant": str(m.variant_id),
                "description": variant_label(m.variant),
                "quantity": f"{m.quantity.normalize():f}",
                "unit_cost_base": str(m.unit_cost_base),
                "note": m.note,
                "created_by_name": person(m.created_by),
                "created_at": m.created_at.isoformat(),
                "returned": m.reversed_at is not None,
                "reversal_reason": m.reversal_reason,
            }
            for m in order.materials.all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not has_permission(request.membership, "inventory.costs"):
            for material in data["materials"]:
                material.pop("unit_cost_base", None)
        else:
            data["material_cost_base"] = str(
                sum((m.quantity * m.unit_cost_base for m in instance.materials.all() if not m.reversed_at), Decimal("0")).quantize(
                    Decimal("0.01")
                )
            )
        return data


# ---------- views ----------


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    filter_backends = [SearchFilter]
    search_fields = ("number", "title", "customer__name", "customer__phone")
    PERMISSIONS = {
        "list": "orders.view",
        "retrieve": "orders.view",
        "create": "orders.create",
        "partial_update": "orders.update",
        "status": "orders.update",
        "cancel": "orders.manage",
        "pay": "orders.payments",
        "materials": "orders.update",
        "return_material": "orders.manage",
        "staff": "orders.view",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_serializer_class(self):
        return OrderSummarySerializer if self.action == "list" else OrderDetailSerializer

    def scoped(self):
        membership = self.request.membership
        return CustomOrder.objects.filter(
            organization_id=membership.organization_id,
            section_id__in=allowed_section_ids(membership),
            branch_id__in=allowed_branch_ids(membership),
        )

    def get_queryset(self):
        queryset = (
            self.scoped()
            .select_related("customer", "section", "assigned_to", "created_by", "photography", "printing__product", "clothing__product")
            .prefetch_related(
                "clothing_items",
                "status_events__actor",
                "allocations__payment__created_by",
                "materials__variant__product",
                "materials__created_by",
            )
        )
        params = self.request.query_params
        for param, field in (("kind", "kind"), ("section", "section_id"), ("customer", "customer_id"), ("status", "status")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        if params.get("assigned") == "me":
            queryset = queryset.filter(assigned_to=self.request.user)
        return self.filter_view(queryset, params.get("view", "active"))

    @staticmethod
    def filter_view(queryset, view):
        today = timezone.localdate()
        open_q = ~Q(status__in=CLOSED_STATUSES)
        if view == "active":
            return queryset.filter(open_q).order_by("due_date", "created_at")
        if view == "due_soon":
            return queryset.filter(open_q, due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS)).order_by("due_date")
        if view == "overdue":
            return queryset.filter(open_q, due_date__lt=today).order_by("due_date")
        if view == "unpaid":
            return queryset.exclude(status="cancelled").filter(paid_amount__lt=F("total")).order_by("due_date")
        if view == "delivered":
            return queryset.filter(status="delivered").order_by("-delivered_at")
        if view == "cancelled":
            return queryset.filter(status="cancelled").order_by("-cancelled_at")
        return queryset.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        today = timezone.localdate()
        base = self.scoped().exclude(status__in=CLOSED_STATUSES)
        if request.query_params.get("assigned") == "me":
            base = base.filter(assigned_to=request.user)
        if request.query_params.get("kind"):
            base = base.filter(kind=request.query_params["kind"])
        response.data["counts"] = base.aggregate(
            active=Count("id"),
            due_soon=Count("id", filter=Q(due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS))),
            overdue=Count("id", filter=Q(due_date__lt=today)),
        )
        return response

    def _detail(self, order, status=200):
        order = self.get_queryset_for_detail().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data, status=status)

    def get_queryset_for_detail(self):
        return (
            self.scoped()
            .select_related("customer", "section", "assigned_to", "created_by", "photography", "printing__product", "clothing__product")
            .prefetch_related(
                "clothing_items",
                "status_events__actor",
                "allocations__payment__created_by",
                "materials__variant__product",
                "materials__created_by",
            )
        )

    def get_object(self):
        order = self.get_queryset_for_detail().filter(pk=self.kwargs["pk"]).first()
        if order is None:
            raise NotFound("Order not found.")
        self.check_object_permissions(self.request, order)
        return order

    def _input(self, request, order=None, partial=False):
        serializer = OrderInput(data=request.data, partial=partial, context={"request": request, "order": order})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def create(self, request):
        data = self._input(request)
        title = (data.get("title") or "").strip() or default_title(data["kind"], data["detail"], data.get("items"))

        def handler():
            order = services.create_order(
                membership=request.membership,
                actor=request.user,
                request=request,
                section=data["section"],
                branch=data["branch"],
                customer=data["customer"],
                currency=data["currency"],
                total=data["total"],
                due_date=data["due_date"],
                title=title,
                detail=data["detail"],
                items=data.get("items"),
                assigned_to=data.get("assigned_to"),
                production_cost=data.get("production_cost"),
                notes=data.get("notes", ""),
                deposit=data.get("deposit"),
            )
            return self._detail(order, status=201)

        return run_idempotent(request, organization=request.membership.organization, scope="orders.create", handler=handler, required=True)

    def partial_update(self, request, pk=None):
        order = self.get_object()
        data = self._input(request, order=order, partial=True)
        data.pop("kind", None)
        if "title" in data and not data["title"].strip():
            data.pop("title")
        order = services.update_order(order, membership=request.membership, actor=request.user, data=data, request=request)
        return self._detail(order)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        order = services.change_status(
            self.get_object(),
            membership=request.membership,
            actor=request.user,
            to_status=str(request.data.get("status", "")),
            note=str(request.data.get("note", "")),
            request=request,
        )
        return self._detail(order)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = services.cancel_order(self.get_object(), actor=request.user, reason=str(request.data.get("reason", "")), request=request)
        return self._detail(order)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self.get_object()
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def handler():
            pay_order(
                order,
                amount=data["amount"],
                method=data["method"],
                reference=data.get("reference", ""),
                amount_tendered=data.get("amount_tendered"),
                actor=request.user,
                request=request,
            )
            return self._detail(order, status=201)

        return run_idempotent(request, organization=order.organization, scope="orders.pay", handler=handler, required=True)

    @action(detail=True, methods=["post"])
    def materials(self, request, pk=None):
        order = self.get_object()
        variant_id, quantity = request.data.get("variant"), request.data.get("quantity")
        variant = (
            ProductVariant.objects.select_related("product")
            .filter(pk=variant_id, product__organization_id=request.membership.organization_id)
            .first()
            if variant_id
            else None
        )
        if variant is None:
            raise ValidationError({"variant": ["Choose a stocked product."]})
        try:
            quantity = Decimal(str(quantity))
        except Exception:
            raise ValidationError({"quantity": ["Enter a quantity."]}) from None
        services.use_material(
            order, actor=request.user, variant=variant, quantity=quantity, note=str(request.data.get("note", "")), request=request
        )
        return self._detail(order, status=201)

    @action(detail=True, methods=["post"], url_path=r"materials/(?P<material_id>[^/.]+)/return")
    def return_material(self, request, pk=None, material_id=None):
        order = self.get_object()
        material = OrderMaterial.objects.filter(order=order, pk=material_id).first()
        if material is None:
            raise ValidationError({"material": ["Material line not found on this order."]})
        services.return_material(material, actor=request.user, reason=str(request.data.get("reason", "")), request=request)
        return self._detail(order)

    @action(detail=False, methods=["get"])
    def staff(self, request):
        section = BusinessSection.objects.filter(
            pk=request.query_params.get("section"), organization_id=request.membership.organization_id
        ).first()
        if section is None or section.pk not in allowed_section_ids(request.membership):
            raise ValidationError({"section": ["Choose a section you have access to."]})
        return Response([{"id": s["id"], "name": s["name"]} for s in eligible_staff(request.membership.organization, section)])
