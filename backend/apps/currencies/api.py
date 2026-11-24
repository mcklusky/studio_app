from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.currencies.models import Currency, ExchangeRate
from apps.currencies.services import current_rate
from apps.identity.permissions import HasBusinessPermission


class ExchangeRateSerializer(serializers.ModelSerializer):
    currency = serializers.ChoiceField(choices=[(Currency.LRD, "Liberian Dollar")], default=Currency.LRD)
    units_per_usd = serializers.DecimalField(max_digits=16, decimal_places=6)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeRate
        fields = ("id", "currency", "units_per_usd", "effective_date", "note", "created_by_name", "created_at")
        read_only_fields = ("id", "created_at")

    def get_created_by_name(self, rate):
        return rate.created_by.get_full_name() or rate.created_by.get_username()

    def validate_units_per_usd(self, value):
        if value <= 0:
            raise serializers.ValidationError("Enter a rate greater than zero.")
        return value

    def validate_effective_date(self, value):
        today = timezone.localdate()
        if value > today + timedelta(days=1):
            raise serializers.ValidationError("Rates can be entered for today, tomorrow or earlier dates only.")
        return value


class ExchangeRateViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Any member can read rates (needed to price LRD transactions); only fx.manage can add them."""

    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = ExchangeRateSerializer

    def get_required_permission(self, _request):
        return "fx.manage" if self.action == "create" else "fx.view"

    def get_queryset(self):
        queryset = ExchangeRate.objects.filter(organization_id=self.request.membership.organization_id).select_related("created_by")
        if self.request.query_params.get("currency"):
            queryset = queryset.filter(currency=self.request.query_params["currency"])
        return queryset

    def perform_create(self, serializer):
        organization = self.request.membership.organization
        with transaction.atomic():
            rate = serializer.save(organization=organization, created_by=self.request.user)
            record_event(
                organization=organization,
                action="exchange_rate.created",
                entity=rate,
                request=self.request,
                summary={
                    "currency": rate.currency,
                    "units_per_usd": str(rate.units_per_usd),
                    "effective_date": rate.effective_date.isoformat(),
                },
            )

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Rates in force today (or on ?date=YYYY-MM-DD) for each non-base currency."""
        from apps.common.filters import date_param

        on_date = date_param(request, "date") or timezone.localdate()
        result = {"base_currency": "USD", "date": on_date.isoformat(), "rates": {}}
        for code in (c for c in Currency.values if c != Currency.USD):
            rate = current_rate(request.membership.organization, code, on_date)
            result["rates"][code] = (
                None
                if rate is None
                else {
                    "units_per_usd": str(rate.units_per_usd),
                    "effective_date": rate.effective_date.isoformat(),
                    "is_today": rate.effective_date == on_date,
                }
            )
        return Response(result)
