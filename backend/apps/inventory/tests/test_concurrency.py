"""Simultaneous requests against the same stock, sale or number sequence (PostgreSQL only).

SQLite serializes every write, so these races only exist on PostgreSQL, where the
row locks in apply_movement, next_number and the payment services do the work.
CI runs the suite on PostgreSQL; locally: DATABASE_URL=postgresql://... manage.py test
"""

import threading
from decimal import Decimal
from unittest import skipUnless

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.catalog.models import Customer, Product
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import apply_movement, ensure_default_variant, reconcile
from apps.payments.models import CustomerPaymentAllocation
from apps.sales.models import Sale


def race(count, request):
    """Run request(i) in `count` threads released at the same moment; return the responses."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results[i] = request(i)
        except Exception as exc:  # surfaced by the assertions below
            results[i] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


@skipUnless(connection.vendor == "postgresql", "row-lock races need PostgreSQL")
class ConcurrentStockTests(TransactionTestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.section = self.org.sections.get(code="clothing")
        self.branch = self.org.branches.get()
        self.shirt = Product.objects.create(organization=self.org, section=self.section, name="Shirt", selling_price_base=Decimal("12.00"))
        self.variant = ensure_default_variant(self.shirt)
        self.customer = Customer.objects.create(organization=self.org, name="Amara Sesay")
        self.cashiers = [add_member(self.org, f"cashier{i}", "cashier", all_sections=True) for i in range(6)]

    def stock(self, quantity):
        apply_movement(
            organization=self.org,
            variant=self.variant,
            branch=self.branch,
            quantity_delta=Decimal(quantity),
            movement_type=StockMovement.Type.OPENING,
            actor=self.owner,
            unit_cost_base=Decimal("5.00"),
        )

    def sell(self, i, quantity="1", **extra):
        body = {
            "section": str(self.section.pk),
            "currency": "USD",
            "items": [{"product": str(self.shirt.pk), "quantity": quantity}],
            **extra,
        }
        return client_for(self.cashiers[i]).post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY=f"race-{i}")

    def assert_ledger_matches(self):
        ledger, balance = reconcile(self.variant, self.branch)
        self.assertEqual(ledger, balance)
        self.assertEqual(StockBalance.objects.get(variant=self.variant, branch=self.branch).quantity, balance)
        return balance

    def test_last_unit_is_sold_once(self):
        self.stock("1")
        responses = race(4, lambda i: self.sell(i, payment={"amount": "12.00", "method": "cash"}))
        codes = sorted(getattr(r, "status_code", repr(r)) for r in responses)
        self.assertEqual(codes, [201, 400, 400, 400])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.assert_ledger_matches(), Decimal("0"))

    def test_parallel_sales_get_unique_numbers_and_exact_stock(self):
        self.stock("10")
        responses = race(6, lambda i: self.sell(i, payment={"amount": "12.00", "method": "cash"}))
        self.assertEqual([getattr(r, "status_code", repr(r)) for r in responses], [201] * 6)
        numbers = sorted(r.data["number"] for r in responses)
        self.assertEqual(numbers, [f"INV-{n:04d}" for n in range(1, 7)])
        self.assertEqual(self.assert_ledger_matches(), Decimal("4"))

    def test_balance_cannot_be_paid_twice(self):
        self.stock("5")
        sale = self.sell(0, quantity="2", customer=str(self.customer.pk)).data
        self.assertEqual(sale["balance_due"], "24.00")
        url = f"/api/v1/sales/{sale['id']}/payments/"
        responses = race(
            3,
            lambda i: client_for(self.cashiers[i]).post(
                url, {"amount": "24.00", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY=f"pay-{i}"
            ),
        )
        codes = sorted(getattr(r, "status_code", repr(r)) for r in responses)
        self.assertEqual(codes, [201, 400, 400])
        paid = sum(a.amount for a in CustomerPaymentAllocation.objects.filter(sale_id=sale["id"], payment__reversed_at__isnull=True))
        self.assertEqual(paid, Decimal("24.00"))
        self.assertEqual(Sale.objects.get(pk=sale["id"]).paid_amount, Decimal("24.00"))
