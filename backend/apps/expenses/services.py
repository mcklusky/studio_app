from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.common.numbering import next_number
from apps.currencies.services import snapshot_for
from apps.expenses.models import Expense

CENTS = Decimal("0.01")


@transaction.atomic
def record_expense(
    *, organization, actor, category, section, branch, expense_date, description, method, amount, currency, reference="", request=None
):
    amount = Decimal(amount).quantize(CENTS)
    if amount <= 0:
        raise ValidationError({"amount": ["Enter an amount greater than zero."]})
    if expense_date > timezone.localdate():
        raise ValidationError({"expense_date": ["Expense date cannot be in the future."]})
    if not description.strip():
        raise ValidationError({"description": ["Describe what this expense was for."]})
    fx = snapshot_for(organization, currency, expense_date)
    expense = Expense.objects.create(
        organization=organization,
        number=next_number(organization, "EXP"),
        category=category,
        section=section,
        branch=branch,
        expense_date=expense_date,
        description=description.strip()[:240],
        method=method,
        reference=(reference or "")[:80],
        amount=amount,
        currency=currency,
        fx_units_per_usd=fx.units_per_usd,
        fx_rate_to_base=fx.rate_to_base,
        fx_rate_date=fx.rate_date,
        base_amount=fx.to_base(amount),
        recorded_by=actor,
    )
    record_event(
        organization=organization,
        action="expense.recorded",
        entity=expense,
        actor=actor,
        request=request,
        summary={"number": expense.number, "category": category.name, "amount": str(amount), "currency": currency},
    )
    return expense


@transaction.atomic
def reverse_expense(expense, *, actor, reason, request=None):
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this expense is being reversed."]})
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != Expense.Status.POSTED:
        raise Conflict("This expense has already been reversed.")
    expense.status = Expense.Status.REVERSED
    expense.reversed_at = timezone.now()
    expense.reversed_by = actor
    expense.reversal_reason = reason.strip()[:240]
    expense.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason"])
    record_event(
        organization=expense.organization,
        action="expense.reversed",
        entity=expense,
        actor=actor,
        request=request,
        summary={"number": expense.number, "reason": expense.reversal_reason},
    )
    return expense
