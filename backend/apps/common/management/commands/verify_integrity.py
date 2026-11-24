"""Check that the books agree with themselves. Run after every restore, and any time something looks off.

    python manage.py verify_integrity

Checks (each must hold exactly):
* Stock: every balance equals the sum of its movement ledger; no negative stock.
* Sales/orders: paid_amount equals the posted payment allocations against them.
* Customer payments: allocations of each posted payment add up to the payment.
* Purchases: paid_amount equals the posted supplier payment allocations.
* Sales: total = lines − sale discount.
* Files: every attachment's stored file exists.
Exits with status 1 if anything is wrong, listing what and where.
"""

from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

ZERO = Decimal("0")


class Command(BaseCommand):
    help = "Verify stock ledgers, payment allocations, totals and stored files agree. Exit 1 on any mismatch."

    def handle(self, *args, **options):
        from apps.files.models import Attachment
        from apps.files.services import private_storage
        from apps.inventory.models import StockBalance, StockMovement
        from apps.orders.models import CustomOrder
        from apps.payments.models import CustomerPayment, CustomerPaymentAllocation, SupplierPaymentAllocation
        from apps.purchasing.models import Purchase
        from apps.sales.models import Sale

        problems = []

        self.stdout.write("Record counts:")
        for label in (
            "organizations.Organization",
            "identity.Membership",
            "catalog.Customer",
            "catalog.Product",
            "sales.Sale",
            "orders.CustomOrder",
            "payments.CustomerPayment",
            "purchasing.Purchase",
            "expenses.Expense",
            "inventory.StockMovement",
            "files.Attachment",
            "audit.AuditEvent",
        ):
            self.stdout.write(f"  {label:<28} {apps.get_model(label).objects.count():>8}")

        ledger = {
            (r["variant_id"], r["branch_id"]): r["q"] or ZERO
            for r in StockMovement.objects.values("variant_id", "branch_id").annotate(q=Sum("quantity_delta"))
        }
        for balance in StockBalance.objects.select_related("variant__product"):
            expected = Decimal(ledger.pop((balance.variant_id, balance.branch_id), ZERO))
            if balance.quantity != expected:
                problems.append(
                    f"Stock {balance.variant.product.name}: balance {balance.quantity.normalize():f} but ledger {expected.normalize():f}"
                )
            if balance.quantity < 0:
                problems.append(f"Stock {balance.variant.product.name}: negative quantity {balance.quantity}")
        for (variant_id, branch_id), quantity in ledger.items():
            if quantity:
                problems.append(f"Stock variant {variant_id} at branch {branch_id}: ledger {quantity} but no balance row")

        posted = Q(payment__status=CustomerPayment.Status.POSTED)
        for model, field, label in ((Sale, "sale_id", "Sale"), (CustomOrder, "custom_order_id", "Order")):
            allocated = {
                r[field]: r["t"]
                for r in CustomerPaymentAllocation.objects.filter(posted, **{f"{field}__isnull": False})
                .values(field)
                .annotate(t=Sum("amount"))
            }
            for doc in model.objects.only("number", "paid_amount"):
                if doc.paid_amount != allocated.get(doc.pk, ZERO):
                    problems.append(f"{label} {doc.number}: paid {doc.paid_amount} but payments applied {allocated.get(doc.pk, ZERO)}")

        for payment in CustomerPayment.objects.filter(status=CustomerPayment.Status.POSTED).annotate(t=Sum("allocations__amount")):
            if (payment.t or ZERO) != payment.amount:
                problems.append(f"Payment {payment.number}: amount {payment.amount} but allocated {payment.t or ZERO}")

        supplier_allocated = {
            r["purchase_id"]: r["t"]
            for r in SupplierPaymentAllocation.objects.filter(payment__status="posted").values("purchase_id").annotate(t=Sum("amount"))
        }
        for purchase in Purchase.objects.only("number", "paid_amount"):
            if purchase.paid_amount != supplier_allocated.get(purchase.pk, ZERO):
                problems.append(
                    f"Purchase {purchase.number}: paid {purchase.paid_amount} but payments applied {supplier_allocated.get(purchase.pk, ZERO)}"
                )

        for sale in Sale.objects.annotate(lines_total=Sum("lines__line_total")):
            if (sale.lines_total or ZERO) - sale.sale_discount != sale.total:
                problems.append(
                    f"Sale {sale.number}: total {sale.total} but lines − discount = {(sale.lines_total or ZERO) - sale.sale_discount}"
                )

        storage = private_storage()
        missing = [a for a in Attachment.objects.only("storage_key", "original_name") if not storage.exists(a.storage_key)]
        for attachment in missing[:50]:
            problems.append(f"File missing from storage: {attachment.original_name} ({attachment.storage_key})")
        if len(missing) > 50:
            problems.append(f"... and {len(missing) - 50} more missing files")

        if problems:
            self.stderr.write(self.style.ERROR(f"{len(problems)} problem(s) found:"))
            for problem in problems:
                self.stderr.write(f"  - {problem}")
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All checks passed: stock ledgers, payments, totals and files agree."))
