from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.catalog.models import Customer, Product
from apps.currencies.models import ExchangeRate
from apps.identity.tests.factories import add_member, client_for, make_org
from apps.inventory.models import StockBalance
from apps.inventory.services import adjust_stock, ensure_default_variant
from apps.orders.models import CustomOrder, OrderStatusEvent
from apps.payments.models import CustomerPayment

TODAY = timezone.localdate()


class Base(TestCase):
    def setUp(self):
        self.org, self.owner = make_org("Studio", "owner")
        self.sections = {s.code: s for s in self.org.sections.all()}
        self.customer = Customer.objects.create(organization=self.org, name="Lofa Stars FC", phone="0770000001")
        ExchangeRate.objects.create(
            organization=self.org, currency="LRD", units_per_usd=Decimal("200"), effective_date=TODAY, created_by=self.owner
        )
        self.manager = add_member(self.org, "manager", "manager", all_sections=True)
        self.cashier = add_member(self.org, "cashier", "cashier", all_sections=True)
        self.printer = add_member(self.org, "printer", "department-staff", sections=["printing"])
        self.tailor = add_member(self.org, "tailor", "department-staff", sections=["clothing"])
        self.keys = iter(range(10_000))

    def key(self):
        return f"k{next(self.keys)}"

    def create(self, kind="printing", user=None, **overrides):
        details = {
            "printing": {"detail": {"item": "Banner", "quantity": "2", "size": "3x6 ft", "material": "Flex"}},
            "clothing": {
                "detail": {"item": "Jersey", "color": "Blue/White", "design": "Club crest front"},
                "items": [
                    {"size": "M", "custom_name": "KOFFI", "custom_number": "10"},
                    {"size": "L", "custom_name": "WEAH", "custom_number": "9", "quantity": 2},
                ],
            },
            "photography": {
                "detail": {
                    "shoot_type": "Wedding",
                    "package": "Gold",
                    "shoot_at": (timezone.now() + timedelta(days=5)).isoformat(),
                    "location": "Sinkor",
                }
            },
        }[kind]
        body = {
            "section": str(self.sections[kind].pk),
            "customer": str(self.customer.pk),
            "currency": "USD",
            "total": "120.00",
            "due_date": (TODAY + timedelta(days=7)).isoformat(),
            **details,
            **overrides,
        }
        return client_for(user or self.owner).post("/api/v1/orders/", body, format="json", HTTP_IDEMPOTENCY_KEY=self.key())

    def url(self, order, suffix=""):
        return f"/api/v1/orders/{order['id']}/{suffix}"


class CreateOrderTests(Base):
    def test_printing_order_with_deposit(self):
        response = self.create(deposit={"amount": "50.00", "method": "mobile_money", "reference": "MM-1"})
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual((data["number"], data["kind"], data["status"]), ("ORD-0001", "printing", "pending"))
        self.assertEqual((data["paid_amount"], data["balance_due"]), ("50.00", "70.00"))
        self.assertEqual(data["title"], "Banner × 2")
        self.assertEqual(data["detail"]["size"], "3x6 ft")
        self.assertEqual(len(data["payments"]), 1)
        self.assertEqual(len(data["history"]), 1)

    def test_clothing_keeps_size_name_number_lines(self):
        data = self.create("clothing").data
        self.assertEqual(data["title"], "Jersey × 3")
        self.assertEqual(
            [(i["size"], i["custom_name"], i["custom_number"], i["quantity"]) for i in data["items"]],
            [("M", "KOFFI", "10", 1), ("L", "WEAH", "9", 2)],
        )
        self.assertEqual(self.create("clothing", items=[]).status_code, 400)

    def test_photography_booking_uses_lrd_snapshot(self):
        data = self.create("photography", currency="LRD", total="30000").data
        self.assertEqual((data["status"], data["base_total"], data["title"]), ("booked", "150.00", "Wedding · Gold"))
        self.assertIsNotNone(data["shoot_at"])

    def test_validation(self):
        self.assertIn("due_date", self.create(due_date=(TODAY - timedelta(days=1)).isoformat()).data["error"]["field_errors"])
        self.assertIn("detail.item", self.create(detail={"quantity": "1"}).data["error"]["field_errors"])
        self.assertIn("deposit.amount", self.create(deposit={"amount": "500", "method": "cash"}).data["error"]["field_errors"])
        retail = self.org.sections.create(name="Retail", code="retail")
        self.assertIn("section", self.create(section=str(retail.pk)).data["error"]["field_errors"])
        no_key = client_for(self.owner).post("/api/v1/orders/", {}, format="json")
        self.assertEqual(no_key.status_code, 400)

    def test_orders_do_not_touch_stock(self):
        shirt = ensure_default_variant(Product.objects.create(organization=self.org, section=self.sections["clothing"], name="Blank tee"))
        adjust_stock(
            organization=self.org,
            variant=shirt,
            branch=self.org.branches.first(),
            quantity_delta=10,
            reason="opening",
            actor=self.owner,
            unit_cost_base=Decimal("3"),
        )
        self.create("clothing", detail={"item": "Tee", "product": str(shirt.product_id)})
        self.assertEqual(StockBalance.objects.get(variant=shirt).quantity, Decimal("10"))


class ScopeAndPermissionTests(Base):
    def test_department_staff_only_see_their_section(self):
        self.create("printing")
        self.create("clothing")
        printer_rows = client_for(self.printer).get("/api/v1/orders/").data["results"]
        self.assertEqual([r["kind"] for r in printer_rows], ["printing"])
        self.assertEqual(self.create("clothing", user=self.printer).status_code, 400)

    def test_assignee_must_work_in_section(self):
        response = self.create(assigned_to=self.tailor.pk)
        self.assertIn("assigned_to", response.data["error"]["field_errors"])
        ok = self.create(assigned_to=self.printer.pk)
        self.assertEqual(ok.data["assigned_to_name"], "printer")
        staff = client_for(self.owner).get(f"/api/v1/orders/staff/?section={self.sections['printing'].pk}").data
        self.assertIn("printer", [s["name"] for s in staff])
        self.assertNotIn("tailor", [s["name"] for s in staff])

    def test_cashier_can_take_payment_but_not_create(self):
        order = self.create().data
        self.assertEqual(self.create(user=self.cashier).status_code, 403)
        pay = client_for(self.cashier).post(
            self.url(order, "pay/"), {"amount": "20.00", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY=self.key()
        )
        self.assertEqual(pay.status_code, 201, pay.data)
        self.assertEqual(pay.data["paid_amount"], "20.00")
        too_much = client_for(self.cashier).post(
            self.url(order, "pay/"), {"amount": "101.00", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY=self.key()
        )
        self.assertEqual(too_much.status_code, 400)


class WorkflowTests(Base):
    def test_forward_steps_and_delivery(self):
        order = self.create(user=self.printer).data
        printer = client_for(self.printer)
        self.assertEqual(printer.post(self.url(order, "status/"), {"status": "designing"}, format="json").data["status"], "designing")
        skipped = printer.post(self.url(order, "status/"), {"status": "completed"}, format="json").data
        self.assertEqual(skipped["status"], "completed")
        done = printer.post(self.url(order, "status/"), {"status": "delivered"}, format="json").data
        self.assertIsNotNone(done["delivered_at"])
        self.assertEqual([h["to"] for h in done["history"]], ["pending", "designing", "completed", "delivered"])
        # closed orders are not editable
        self.assertEqual(printer.patch(self.url(order), {"notes": "x"}, format="json").status_code, 409)

    def test_backwards_is_a_manager_correction_with_note(self):
        order = self.create().data
        client_for(self.printer).post(self.url(order, "status/"), {"status": "production"}, format="json")
        self.assertEqual(client_for(self.printer).post(self.url(order, "status/"), {"status": "designing"}, format="json").status_code, 403)
        self.assertEqual(client_for(self.manager).post(self.url(order, "status/"), {"status": "designing"}, format="json").status_code, 400)
        fixed = client_for(self.manager).post(
            self.url(order, "status/"), {"status": "designing", "note": "Client changed artwork"}, format="json"
        )
        self.assertEqual(fixed.status_code, 200)
        self.assertTrue(OrderStatusEvent.objects.filter(order_id=order["id"], is_correction=True).exists())
        self.assertTrue(AuditEvent.objects.filter(action="order.status_corrected").exists())

    def test_invalid_status(self):
        order = self.create().data
        self.assertEqual(client_for(self.owner).post(self.url(order, "status/"), {"status": "booked"}, format="json").status_code, 400)

    def test_price_change_needs_manager_and_cannot_drop_below_paid(self):
        order = self.create(deposit={"amount": "100.00", "method": "cash"}).data
        self.assertEqual(client_for(self.printer).patch(self.url(order), {"total": "150.00"}, format="json").status_code, 403)
        self.assertEqual(client_for(self.manager).patch(self.url(order), {"total": "90.00"}, format="json").status_code, 400)
        updated = client_for(self.manager).patch(self.url(order), {"total": "150.00"}, format="json").data
        self.assertEqual((updated["total"], updated["balance_due"]), ("150.00", "50.00"))
        spec = client_for(self.printer).patch(self.url(order), {"detail": {"item": "Banner", "quantity": "4"}}, format="json")
        self.assertEqual(spec.data["detail"]["quantity"], "4")
        self.assertEqual(client_for(self.printer).patch(self.url(order), {"currency": "LRD"}, format="json").status_code, 400)

    def test_cancel_requires_no_payments(self):
        order = self.create(deposit={"amount": "10.00", "method": "cash"}).data
        self.assertEqual(client_for(self.printer).post(self.url(order, "cancel/"), {"reason": "x"}, format="json").status_code, 403)
        self.assertEqual(
            client_for(self.manager).post(self.url(order, "cancel/"), {"reason": "Client withdrew"}, format="json").status_code, 409
        )
        payment = CustomerPayment.objects.get()
        client_for(self.manager).post(f"/api/v1/customer-payments/{payment.pk}/reverse/", {"reason": "Refunded deposit"}, format="json")
        cancelled = client_for(self.manager).post(self.url(order, "cancel/"), {"reason": "Client withdrew"}, format="json")
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertEqual(
            client_for(self.cashier)
            .post(self.url(order, "pay/"), {"amount": "1", "method": "cash"}, format="json", HTTP_IDEMPOTENCY_KEY=self.key())
            .status_code,
            409,
        )

    def test_due_filters_and_counts(self):
        self.create(due_date=(TODAY + timedelta(days=1)).isoformat())
        late = self.create(due_date=(TODAY + timedelta(days=1)).isoformat()).data
        CustomOrder.objects.filter(pk=late["id"]).update(due_date=TODAY - timedelta(days=2))
        self.create(due_date=(TODAY + timedelta(days=20)).isoformat())
        data = client_for(self.owner).get("/api/v1/orders/?view=overdue").data
        self.assertEqual([r["number"] for r in data["results"]], [late["number"]])
        self.assertTrue(data["results"][0]["overdue"])
        self.assertEqual(data["counts"], {"active": 3, "due_soon": 1, "overdue": 1})
        # Closed orders are still retrievable by id.
        self.assertEqual(client_for(self.owner).get(self.url(late)).status_code, 200)


class BalanceAndMaterialTests(Base):
    def test_customer_balance_and_payment_cover_orders(self):
        order = self.create(total="80.00").data
        rows = client_for(self.owner).get("/api/v1/customers/?has_balance=true").data["results"]
        self.assertEqual(rows[0]["balances"], {"USD": "80.00"})
        statement = client_for(self.owner).get(f"/api/v1/customers/{self.customer.pk}/statement/").data
        self.assertEqual(statement["open_documents"][0]["kind"], "order")
        payment = client_for(self.cashier).post(
            "/api/v1/customer-payments/",
            {"customer": str(self.customer.pk), "currency": "USD", "amount": "30.00", "method": "cash"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assertEqual(payment.status_code, 201, payment.data)
        self.assertEqual(
            payment.data["allocations"][0], {"document": order["id"], "kind": "order", "number": order["number"], "amount": "30.00"}
        )
        self.assertEqual(CustomOrder.objects.get(pk=order["id"]).paid_amount, Decimal("30.00"))

    def test_materials_move_stock_explicitly_and_can_be_returned(self):
        tee = ensure_default_variant(Product.objects.create(organization=self.org, section=self.sections["clothing"], name="Blank tee"))
        adjust_stock(
            organization=self.org,
            variant=tee,
            branch=self.org.branches.first(),
            quantity_delta=10,
            reason="opening",
            actor=self.owner,
            unit_cost_base=Decimal("3"),
        )
        order = self.create("clothing", user=self.tailor).data
        used = client_for(self.tailor).post(self.url(order, "materials/"), {"variant": str(tee.pk), "quantity": "3"}, format="json")
        self.assertEqual(used.status_code, 201, used.data)
        self.assertNotIn("unit_cost_base", used.data["materials"][0])  # staff cannot see costs
        self.assertEqual(StockBalance.objects.get(variant=tee).quantity, Decimal("7"))
        too_many = client_for(self.tailor).post(self.url(order, "materials/"), {"variant": str(tee.pk), "quantity": "50"}, format="json")
        self.assertEqual(too_many.status_code, 400)
        owner_view = client_for(self.owner).get(self.url(order)).data
        self.assertEqual(owner_view["material_cost_base"], "9.00")
        material_id = owner_view["materials"][0]["id"]
        back = client_for(self.manager).post(self.url(order, f"materials/{material_id}/return/"), {"reason": "Not needed"}, format="json")
        self.assertEqual(back.status_code, 200, back.data)
        self.assertEqual(StockBalance.objects.get(variant=tee).quantity, Decimal("10"))
        self.assertEqual(StockBalance.objects.get(variant=tee).average_cost_base, Decimal("3.0000"))
