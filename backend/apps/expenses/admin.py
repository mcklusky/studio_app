from django.contrib import admin

from apps.expenses.models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "active")
    list_filter = ("organization", "active")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("number", "expense_date", "category", "amount", "currency", "status", "organization")
    list_filter = ("organization", "section", "branch", "currency", "status")
    date_hierarchy = "expense_date"
