from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from apps.expenses.models import Expense, ExpenseCategory
from apps.identity.scope import allowed_branch_ids, allowed_section_ids


class ExpenseCategorySerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = ("id", "organization_id", "name", "active", "created_at")
        read_only_fields = ("id", "created_at")


class ExpenseSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    base_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    fx_rate_to_base = serializers.DecimalField(max_digits=16, decimal_places=8, required=False)
    status = serializers.CharField(read_only=True)
    recorded_by = serializers.UUIDField(source="recorded_by_id", read_only=True)

    class Meta:
        model = Expense
        fields = ("id", "organization_id", "category", "section", "branch", "amount", "currency", "fx_rate_to_base", "base_amount", "occurred_at", "description", "status", "recorded_by", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        membership = self.context["request"].membership
        section = attrs.get("section", getattr(self.instance, "section", None))
        branch = attrs.get("branch", getattr(self.instance, "branch", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        currency = attrs.get("currency", getattr(self.instance, "currency", None))
        rate = attrs.get("fx_rate_to_base", getattr(self.instance, "fx_rate_to_base", None))
        if not section or section.organization_id != membership.organization_id or section.id not in allowed_section_ids(membership):
            raise serializers.ValidationError({"section": "Choose a section available in your organization."})
        if branch and (branch.organization_id != membership.organization_id or branch.id not in allowed_branch_ids(membership)):
            raise serializers.ValidationError({"branch": "Choose a branch available in your organization."})
        if not category or category.organization_id != membership.organization_id:
            raise serializers.ValidationError({"category": "Choose an expense category in this organization."})
        if self.instance and self.instance.status != Expense.Status.DRAFT:
            raise serializers.ValidationError("Only draft expenses can be edited.")
        if currency == Expense.Currency.USD:
            rate = Decimal("1")
            attrs["fx_rate_to_base"] = rate
        elif currency == Expense.Currency.LRD and not self.initial_data.get("fx_rate_to_base"):
            raise serializers.ValidationError({"fx_rate_to_base": "Enter the provisional LRD-to-USD rate for this draft."})
        if amount is not None and rate is not None:
            attrs["base_amount"] = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return attrs
