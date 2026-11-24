"""Application permission catalog and the starter (system) roles.

These are provisional defaults from docs/discovery-decisions.md. Run
`manage.py sync_access` after editing so existing organizations pick up changes.
"""

from django.db import transaction

from apps.identity.models import AccessPermission, Role

PERMISSIONS = {
    "organization.view": "View organization settings",
    "organization.manage": "Update organization settings",
    "staff.manage": "Manage staff accounts and memberships",
    "website.manage": "Edit the public website details and handle website requests",
    "roles.manage": "Manage organization roles and permissions",
    "dashboard.view": "View dashboard summaries",
    "sales.view": "View sales",
    "sales.create": "Create sales and record customer payments",
    "sales.reverse": "Reverse (void) posted sales",
    "sales.price_override": "Sell at a price other than the catalog price",
    "orders.view": "View department orders",
    "orders.create": "Create department orders",
    "orders.update": "Update order details, status and materials used",
    "orders.manage": "Change order prices, correct statuses, cancel orders and return materials",
    "orders.payments": "Record deposits and payments on orders",
    "inventory.view": "View inventory",
    "inventory.adjust": "Adjust inventory",
    "inventory.costs": "View inventory costs and stock value",
    "reports.view": "View reports",
    "customers.view": "View customer records",
    "customers.create": "Create customer records",
    "customers.manage": "Update customer records",
    "suppliers.view": "View supplier records",
    "suppliers.create": "Create supplier records",
    "suppliers.manage": "Update supplier records",
    "catalog.view": "View products and categories",
    "catalog.create": "Create products and categories",
    "catalog.manage": "Update products and categories",
    "expenses.view": "View expense records",
    "expenses.create": "Record expenses",
    "expenses.manage": "Manage expense categories and reverse expenses",
    "audit.view": "View the activity audit trail",
    "fx.view": "View exchange rates",
    "fx.manage": "Enter daily exchange rates",
    "purchases.view": "View supplier purchases",
    "purchases.create": "Create, edit and cancel purchases",
    "purchases.receive": "Receive goods and reverse receipts",
    "payables.pay": "Record and reverse payments to suppliers",
}

ROLE_PERMISSIONS = {
    "owner-admin": set(PERMISSIONS),
    "manager": {
        "organization.view",
        "website.manage",
        "dashboard.view",
        "sales.view",
        "sales.create",
        "sales.reverse",
        "sales.price_override",
        "orders.view",
        "orders.create",
        "orders.update",
        "orders.manage",
        "orders.payments",
        "inventory.view",
        "inventory.adjust",
        "inventory.costs",
        "reports.view",
        "customers.view",
        "customers.create",
        "customers.manage",
        "suppliers.view",
        "suppliers.create",
        "suppliers.manage",
        "catalog.view",
        "catalog.create",
        "catalog.manage",
        "expenses.view",
        "expenses.create",
        "expenses.manage",
        "audit.view",
        "fx.view",
        "purchases.view",
        "purchases.create",
        "purchases.receive",
        "payables.pay",
    },
    "cashier": {
        "dashboard.view",
        "sales.view",
        "sales.create",
        "orders.view",
        "orders.payments",
        "customers.view",
        "customers.create",
        "catalog.view",
        "fx.view",
    },
    "department-staff": {
        "dashboard.view",
        "orders.view",
        "orders.create",
        "orders.update",
        "orders.payments",
        "inventory.view",
        "catalog.view",
        "customers.view",
        "fx.view",
    },
}


def role_name(code):
    return code.replace("-", " ").title()


@transaction.atomic
def sync_system_roles(organization):
    """Create missing permissions and set each system role to its catalog definition."""
    permission_objects = {}
    for code, description in PERMISSIONS.items():
        permission, _ = AccessPermission.objects.update_or_create(code=code, defaults={"description": description})
        permission_objects[code] = permission
    roles = {}
    for code, codes in ROLE_PERMISSIONS.items():
        role, _ = Role.objects.get_or_create(organization=organization, code=code, defaults={"name": role_name(code), "is_system": True})
        role.permissions.set([permission_objects[p] for p in codes])
        roles[code] = role
    return roles
