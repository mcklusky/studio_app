"""Currency conversion to the USD reporting base.

Every monetary transaction stores a snapshot: its currency, the quote used
(units per USD, 1 for USD), the rate date, and the base amount. Base amounts
are computed from the quote by division, rounded half-up to cents.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError

from apps.currencies.models import Currency, ExchangeRate

CENTS = Decimal("0.01")
RATE_PLACES = Decimal("0.00000001")


@dataclass(frozen=True)
class FxSnapshot:
    currency: str
    units_per_usd: Decimal
    rate_date: date | None

    @property
    def rate_to_base(self):
        """USD per one unit of the transaction currency (API field fx_rate_to_base)."""
        return (Decimal("1") / self.units_per_usd).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)

    def to_base(self, amount, places=CENTS):
        return (Decimal(amount) / self.units_per_usd).quantize(places, rounding=ROUND_HALF_UP)


def current_rate(organization, currency, on_date):
    """The latest rate effective on or before `on_date`, or None."""
    return (
        ExchangeRate.objects.filter(organization=organization, currency=currency, effective_date__lte=on_date)
        .order_by("-effective_date", "-created_at")
        .first()
    )


def snapshot_for(organization, currency, on_date):
    """FX snapshot to store on a transaction dated `on_date`. Raises 400 if no rate exists."""
    if currency == Currency.USD:
        return FxSnapshot(Currency.USD, Decimal("1"), None)
    if currency not in Currency.values:
        raise ValidationError({"currency": ["Use LRD or USD."]})
    rate = current_rate(organization, currency, on_date)
    if rate is None:
        raise ValidationError(
            {
                "currency": [
                    f"No {currency} exchange rate is set for {on_date:%d %b %Y} or earlier. Ask an owner/admin to enter today's rate."
                ]
            }
        )
    return FxSnapshot(currency, rate.units_per_usd, rate.effective_date)
