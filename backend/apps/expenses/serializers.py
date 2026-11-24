from rest_framework import serializers

from apps.currencies.models import Currency
from apps.expenses.models import Expense, ExpenseCategory
from apps.identity.scope import allowed_branch_ids, allowed_section_ids
from apps.organizations.models import Branch, BusinessSection
from apps.payments.models import PaymentMethod


class ExpenseCategorySerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = ("id", "organization_id", "name", "active", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_name(self, value):
        value = value.strip()
        organization_id = self.context["request"].membership.organization_id
        clash = ExpenseCategory.objects.filter(organization_id=organization_id, name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value


class ExpenseInputSerializer(serializers.Serializer):
    category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    section = serializers.PrimaryKeyRelatedField(queryset=BusinessSection.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    expense_date = serializers.DateField()
    description = serializers.CharField(max_length=240)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.ChoiceField(choices=Currency.choices)

    def validate(self, attrs):
        membership = self.context["request"].membership
        org_id = membership.organization_id
        if attrs["category"].organization_id != org_id or not attrs["category"].active:
            raise serializers.ValidationError({"category": ["Choose an active expense category."]})
        section = attrs["section"]
        if section.organization_id != org_id or section.pk not in allowed_section_ids(membership):
            raise serializers.ValidationError({"section": ["Choose a section you have access to."]})
        allowed = allowed_branch_ids(membership)
        branch = attrs.get("branch")
        if branch is None:
            if len(allowed) != 1:
                raise serializers.ValidationError({"branch": ["Choose a branch."]})
            attrs["branch"] = Branch.objects.get(pk=allowed[0])
        elif branch.pk not in allowed:
            raise serializers.ValidationError({"branch": ["Choose a branch you have access to."]})
        return attrs


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name")
    section_name = serializers.CharField(source="section.name")
    method_label = serializers.CharField(source="get_method_display")
    recorded_by_name = serializers.SerializerMethodField()
    reversed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = (
            "id",
            "number",
            "status",
            "category",
            "category_name",
            "section",
            "section_name",
            "branch",
            "expense_date",
            "description",
            "method",
            "method_label",
            "reference",
            "amount",
            "currency",
            "fx_units_per_usd",
            "fx_rate_to_base",
            "fx_rate_date",
            "base_amount",
            "recorded_by_name",
            "created_at",
            "reversed_at",
            "reversed_by_name",
            "reversal_reason",
        )

    def get_recorded_by_name(self, expense):
        return expense.recorded_by.get_full_name() or expense.recorded_by.get_username()

    def get_reversed_by_name(self, expense):
        user = expense.reversed_by
        return (user.get_full_name() or user.get_username()) if user else None
