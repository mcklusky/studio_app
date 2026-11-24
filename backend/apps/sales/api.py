from decimal import Decimal

from django.db.models import F
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Customer, Product, ProductVariant
from apps.common.filters import date_param
from apps.common.idempotency import run_idempotent
from apps.currencies.models import Currency
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, has_permission
from apps.organizations.models import Branch, BusinessSection
from apps.payments.models import PaymentMethod
from apps.payments.services import pay_sale
from apps.sales import services
from apps.sales.models import Sale

MONEY = {"max_digits": 14, "decimal_places": 2}


# ---------- input ----------


class ItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.prefetch_related("variants"))
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(**MONEY, required=False, allow_null=True)
    discount = serializers.DecimalField(**MONEY, required=False, allow_null=True)


class PaymentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    amount_tendered = serializers.DecimalField(**MONEY, required=False, allow_null=True)


class SaleInputSerializer(serializers.Serializer):
    section = serializers.PrimaryKeyRelatedField(queryset=BusinessSection.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    currency = serializers.ChoiceField(choices=Currency.choices)
    items = ItemInputSerializer(many=True)
    sale_discount = serializers.DecimalField(**MONEY, required=False, allow_null=True)
    payment = PaymentInputSerializer(required=False, allow_null=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        membership = self.context["request"].membership
        org_id = membership.organization_id
        section = attrs["section"]
        if section.organization_id != org_id or section.pk not in allowed_section_ids(membership):
            raise serializers.ValidationError({"section": ["Choose a section you have access to."]})
        allowed_branches = allowed_branch_ids(membership)
        branch = attrs.get("branch")
        if branch is None:
            if len(allowed_branches) != 1:
                raise serializers.ValidationError({"branch": ["Choose a branch."]})
            attrs["branch"] = Branch.objects.get(pk=allowed_branches[0])
        elif branch.pk not in allowed_branches:
            raise serializers.ValidationError({"branch": ["Choose a branch you have access to."]})
        customer = attrs.get("customer")
        if customer is not None and (customer.organization_id != org_id or not customer.active):
            raise serializers.ValidationError({"customer": ["Choose an active customer."]})
        return attrs


# ---------- output ----------


def person(user):
    return (user.get_full_name() or user.get_username()) if user else None


class SaleSummarySerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    section_name = serializers.CharField(source="section.name")
    created_by_name = serializers.SerializerMethodField()
    balance_due = serializers.DecimalField(**MONEY)
    discount_total = serializers.DecimalField(**MONEY)

    class Meta:
        model = Sale
        fields = (
            "id",
            "number",
            "status",
            "section",
            "section_name",
            "customer",
            "customer_name",
            "currency",
            "subtotal",
            "discount_total",
            "total",
            "base_total",
            "paid_amount",
            "balance_due",
            "created_by_name",
            "posted_at",
        )

    def get_customer_name(self, sale):
        return sale.customer.name if sale.customer_id else "Walk-in customer"

    def get_created_by_name(self, sale):
        return person(sale.created_by)


class SaleDetailSerializer(SaleSummarySerializer):
    organization_name = serializers.CharField(source="organization.name")
    customer_phone = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    reversed_by_name = serializers.SerializerMethodField()

    class Meta(SaleSummarySerializer.Meta):
        fields = SaleSummarySerializer.Meta.fields + (
            "organization_name",
            "customer_phone",
            "line_discount_total",
            "sale_discount",
            "fx_units_per_usd",
            "fx_rate_to_base",
            "fx_rate_date",
            "notes",
            "lines",
            "payments",
            "cost_total_base",
            "reversed_at",
            "reversed_by_name",
            "reversal_reason",
        )

    def get_customer_phone(self, sale):
        return sale.customer.phone if sale.customer_id else ""

    def get_reversed_by_name(self, sale):
        return person(sale.reversed_by)

    def get_lines(self, sale):
        return [
            {
                "id": str(line.id),
                "product": str(line.product_id),
                "variant": str(line.variant_id) if line.variant_id else None,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "discount": str(line.discount),
                "line_total": str(line.line_total),
                "price_overridden": line.price_overridden,
                "unit_cost_base": str(line.unit_cost_base) if line.unit_cost_base is not None else None,
            }
            for line in sale.lines.all()
        ]

    def get_payments(self, sale):
        rows = []
        for allocation in sale.allocations.all():
            p = allocation.payment
            rows.append(
                {
                    "id": str(p.id),
                    "number": p.number,
                    "status": p.status,
                    "method": p.method,
                    "method_label": p.get_method_display(),
                    "reference": p.reference,
                    "amount": str(allocation.amount),
                    "amount_tendered": str(p.amount_tendered) if p.amount_tendered is not None else None,
                    "change": str(p.amount_tendered - p.amount) if p.amount_tendered is not None else None,
                    "received_at": p.received_at.isoformat(),
                    "created_by_name": person(p.created_by),
                }
            )
        return rows

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not has_permission(request.membership, "inventory.costs"):
            data.pop("cost_total_base", None)
            for line in data["lines"]:
                line.pop("unit_cost_base", None)
        elif data.get("status") == "posted":
            data["gross_profit_base"] = str((Decimal(data["base_total"]) - Decimal(data["cost_total_base"])).quantize(Decimal("0.01")))
        return data


def priced_payload(priced):
    currency = priced.fx.currency
    return {
        "currency": currency,
        "fx_units_per_usd": str(priced.fx.units_per_usd),
        "lines": [
            {
                "product": str(line.product.pk),
                "variant": str(line.variant.pk) if line.variant else None,
                "description": line.description,
                "quantity": str(line.quantity),
                "list_price": str(line.list_price),
                "unit_price": str(line.unit_price),
                "discount": str(line.discount),
                "line_total": str(line.line_total),
                "available_after": None if line.available is None else f"{line.available.normalize():f}",
                "stock_ok": line.available is None or line.available >= 0,
            }
            for line in priced.lines
        ],
        "subtotal": str(priced.subtotal),
        "discount_total": str(priced.line_discount_total + priced.sale_discount),
        "total": str(priced.total),
        "base_total": str(priced.fx.to_base(priced.total)),
        "stock_ok": not priced.stock_problems,
    }


class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    filter_backends = [SearchFilter]
    search_fields = ("number", "customer__name", "customer__phone")
    PERMISSIONS = {
        "list": "sales.view",
        "retrieve": "sales.view",
        "receipt_pdf": "sales.view",
        "create": "sales.create",
        "preview": "sales.create",
        "add_payment": "sales.create",
        "reverse": "sales.reverse",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_serializer_class(self):
        return SaleSummarySerializer if self.action == "list" else SaleDetailSerializer

    def get_queryset(self):
        membership = self.request.membership
        queryset = (
            Sale.objects.filter(
                organization_id=membership.organization_id,
                section_id__in=allowed_section_ids(membership),
                branch_id__in=allowed_branch_ids(membership),
            )
            .select_related("customer", "section", "created_by", "organization", "reversed_by")
            .prefetch_related("lines", "allocations__payment__created_by")
        )
        params = self.request.query_params
        for param, field in (("status", "status"), ("section", "section_id"), ("customer", "customer_id")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        if params.get("unpaid") == "true":
            queryset = queryset.filter(status=Sale.Status.POSTED, paid_amount__lt=F("total"))
        start, end = date_param(self.request, "from"), date_param(self.request, "to")
        if start:
            queryset = queryset.filter(posted_at__date__gte=start)
        if end:
            queryset = queryset.filter(posted_at__date__lte=end)
        return queryset

    def _input(self, request):
        serializer = SaleInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt_pdf(self, request, pk=None):
        """The customer receipt as a PDF. Same scope as viewing the sale; never contains costs."""
        from django.http import HttpResponse

        from apps.audit.services import record_event
        from apps.sales.receipts import render_receipt_pdf

        sale = self.get_object()
        data = SaleDetailSerializer(sale, context=self.get_serializer_context()).data
        content = render_receipt_pdf(data)
        record_event(
            organization=sale.organization, action="sale.receipt_downloaded", entity=sale, request=request, summary={"number": sale.number}
        )
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="receipt-{sale.number}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response

    def _detail(self, sale, status=200):
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(SaleDetailSerializer(sale, context=self.get_serializer_context()).data, status=status)

    @action(detail=False, methods=["post"])
    def preview(self, request):
        data = self._input(request)
        priced = services.price_sale(
            membership=request.membership,
            section=data["section"],
            branch=data["branch"],
            currency=data["currency"],
            items=data["items"],
            sale_discount=data.get("sale_discount"),
        )
        return Response(priced_payload(priced))

    def create(self, request):
        data = self._input(request)

        def handler():
            sale = services.post_sale(
                membership=request.membership,
                actor=request.user,
                request=request,
                section=data["section"],
                branch=data["branch"],
                currency=data["currency"],
                items=data["items"],
                customer=data.get("customer"),
                sale_discount=data.get("sale_discount") or Decimal("0"),
                payment=data.get("payment"),
                notes=data.get("notes", ""),
            )
            return self._detail(sale, status=201)

        return run_idempotent(request, organization=request.membership.organization, scope="sales.create", handler=handler, required=True)

    @action(detail=True, methods=["post"], url_path="payments")
    def add_payment(self, request, pk=None):
        sale = self.get_object()
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def handler():
            pay_sale(
                sale,
                amount=data["amount"],
                method=data["method"],
                reference=data.get("reference", ""),
                amount_tendered=data.get("amount_tendered"),
                actor=request.user,
                request=request,
            )
            return self._detail(sale, status=201)

        return run_idempotent(request, organization=sale.organization, scope="sales.payment", handler=handler, required=True)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        sale = services.reverse_sale(self.get_object(), actor=request.user, reason=str(request.data.get("reason", "")), request=request)
        return self._detail(sale)
