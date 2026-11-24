from django.db.models import F, Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Customer, Supplier
from apps.common.filters import date_param
from apps.common.idempotency import run_idempotent
from apps.currencies.models import Currency
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_branch_ids, allowed_section_ids
from apps.payments import services
from apps.payments.models import CustomerPayment, PaymentMethod, SupplierPayment
from apps.purchasing.models import Purchase
from apps.sales.models import Sale

MONEY = {"max_digits": 14, "decimal_places": 2}


def person(user):
    return (user.get_full_name() or user.get_username()) if user else None


def scoped_sales(membership):
    return Sale.objects.filter(
        organization_id=membership.organization_id,
        section_id__in=allowed_section_ids(membership),
        branch_id__in=allowed_branch_ids(membership),
    )


def scoped_orders(membership):
    from apps.orders.models import CustomOrder

    return CustomOrder.objects.filter(
        organization_id=membership.organization_id,
        section_id__in=allowed_section_ids(membership),
        branch_id__in=allowed_branch_ids(membership),
    )


def open_customer_documents(membership, customer=None):
    """Unpaid posted sales and unpaid, uncancelled orders the user can see (oldest first)."""
    sales = scoped_sales(membership).filter(status=Sale.Status.POSTED, paid_amount__lt=F("total"))
    orders = scoped_orders(membership).exclude(status="cancelled").filter(paid_amount__lt=F("total"))
    if customer is not None:
        sales, orders = sales.filter(customer=customer), orders.filter(customer=customer)
    return sales, orders


def scoped_purchases(membership):
    return Purchase.objects.filter(
        organization_id=membership.organization_id,
        section_id__in=allowed_section_ids(membership),
        branch_id__in=allowed_branch_ids(membership),
    )


def allocations_input(value):
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise ValidationError({"allocations": ["Send allocations as {document_id: amount}."]})
    return value


# ---------- customer payments ----------


class CustomerPaymentInput(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    currency = serializers.ChoiceField(choices=Currency.choices)
    amount = serializers.DecimalField(**MONEY)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    amount_tendered = serializers.DecimalField(**MONEY, required=False, allow_null=True)
    allocations = serializers.JSONField(required=False)


class CustomerPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", default="Walk-in customer")
    method_label = serializers.CharField(source="get_method_display")
    created_by_name = serializers.SerializerMethodField()
    reversed_by_name = serializers.SerializerMethodField()
    allocations = serializers.SerializerMethodField()

    class Meta:
        model = CustomerPayment
        fields = (
            "id",
            "number",
            "status",
            "customer",
            "customer_name",
            "method",
            "method_label",
            "reference",
            "amount",
            "amount_tendered",
            "currency",
            "base_amount",
            "received_at",
            "created_by_name",
            "reversed_at",
            "reversed_by_name",
            "reversal_reason",
            "allocations",
        )

    def get_created_by_name(self, payment):
        return person(payment.created_by)

    def get_reversed_by_name(self, payment):
        return person(payment.reversed_by)

    def get_allocations(self, payment):
        return [
            {"document": str(a.target_id), "kind": a.target_kind, "number": a.target.number, "amount": str(a.amount)}
            for a in payment.allocations.all()
        ]


class CustomerPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = CustomerPaymentSerializer
    PERMISSIONS = {"list": "sales.view", "retrieve": "sales.view", "create": "sales.create", "reverse": "sales.reverse"}

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_queryset(self):
        membership = self.request.membership
        # Only payments that touch sales or orders the user can see.
        queryset = (
            CustomerPayment.objects.filter(
                Q(allocations__sale__in=scoped_sales(membership)) | Q(allocations__custom_order__in=scoped_orders(membership)),
                organization_id=membership.organization_id,
            )
            .distinct()
            .select_related("customer", "created_by", "reversed_by")
            .prefetch_related("allocations__sale", "allocations__custom_order")
        )
        params = self.request.query_params
        for param, field in (("customer", "customer_id"), ("status", "status"), ("currency", "currency"), ("method", "method")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        start, end = date_param(self.request, "from"), date_param(self.request, "to")
        if start:
            queryset = queryset.filter(received_at__date__gte=start)
        if end:
            queryset = queryset.filter(received_at__date__lte=end)
        return queryset

    def create(self, request):
        serializer = CustomerPaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = request.membership
        if data["customer"].organization_id != membership.organization_id:
            raise ValidationError({"customer": ["Choose a customer in this organization."]})
        sales, orders = open_customer_documents(membership, data["customer"])
        targets = [*sales.filter(currency=data["currency"]), *orders.filter(currency=data["currency"])]

        def handler():
            payment = services.receive_customer_payment(
                organization=membership.organization,
                customer=data["customer"],
                currency=data["currency"],
                amount=data["amount"],
                method=data["method"],
                reference=data.get("reference", ""),
                amount_tendered=data.get("amount_tendered"),
                allocations=allocations_input(data.get("allocations")),
                actor=request.user,
                request=request,
                targets=targets,
            )
            return Response(CustomerPaymentSerializer(self.get_queryset().get(pk=payment.pk)).data, status=201)

        return run_idempotent(
            request, organization=membership.organization, scope="customer_payments.create", handler=handler, required=True
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        payment = services.reverse_customer_payment(
            self.get_object(), actor=request.user, reason=str(request.data.get("reason", "")), request=request
        )
        return Response(CustomerPaymentSerializer(self.get_queryset().get(pk=payment.pk)).data)


# ---------- supplier payments ----------


class SupplierPaymentInput(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    currency = serializers.ChoiceField(choices=Currency.choices)
    amount = serializers.DecimalField(**MONEY)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    paid_on = serializers.DateField(required=False)
    allocations = serializers.JSONField(required=False)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name")
    method_label = serializers.CharField(source="get_method_display")
    created_by_name = serializers.SerializerMethodField()
    reversed_by_name = serializers.SerializerMethodField()
    allocations = serializers.SerializerMethodField()

    class Meta:
        model = SupplierPayment
        fields = (
            "id",
            "number",
            "status",
            "supplier",
            "supplier_name",
            "method",
            "method_label",
            "reference",
            "amount",
            "currency",
            "base_amount",
            "paid_on",
            "created_by_name",
            "created_at",
            "reversed_at",
            "reversed_by_name",
            "reversal_reason",
            "allocations",
        )

    def get_created_by_name(self, payment):
        return person(payment.created_by)

    def get_reversed_by_name(self, payment):
        return person(payment.reversed_by)

    def get_allocations(self, payment):
        return [{"purchase": str(a.purchase_id), "number": a.purchase.number, "amount": str(a.amount)} for a in payment.allocations.all()]


class SupplierPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = SupplierPaymentSerializer
    PERMISSIONS = {"list": "purchases.view", "retrieve": "purchases.view", "create": "payables.pay", "reverse": "payables.pay"}

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_queryset(self):
        membership = self.request.membership
        queryset = (
            SupplierPayment.objects.filter(
                organization_id=membership.organization_id, allocations__purchase__in=scoped_purchases(membership)
            )
            .distinct()
            .select_related("supplier", "created_by", "reversed_by")
            .prefetch_related("allocations__purchase")
        )
        params = self.request.query_params
        for param, field in (
            ("supplier", "supplier_id"),
            ("status", "status"),
            ("currency", "currency"),
            ("purchase", "allocations__purchase_id"),
        ):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        return queryset

    def create(self, request):
        serializer = SupplierPaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = request.membership
        if data["supplier"].organization_id != membership.organization_id:
            raise ValidationError({"supplier": ["Choose a supplier in this organization."]})

        def handler():
            payment = services.pay_supplier(
                organization=membership.organization,
                supplier=data["supplier"],
                currency=data["currency"],
                amount=data["amount"],
                method=data["method"],
                reference=data.get("reference", ""),
                paid_on=data.get("paid_on"),
                allocations=allocations_input(data.get("allocations")),
                actor=request.user,
                request=request,
                section_ids=allowed_section_ids(membership),
            )
            return Response(SupplierPaymentSerializer(self.get_queryset().get(pk=payment.pk)).data, status=201)

        return run_idempotent(
            request, organization=membership.organization, scope="supplier_payments.create", handler=handler, required=True
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        payment = services.reverse_supplier_payment(
            self.get_object(), actor=request.user, reason=str(request.data.get("reason", "")), request=request
        )
        return Response(SupplierPaymentSerializer(self.get_queryset().get(pk=payment.pk)).data)
