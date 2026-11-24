from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.identity.models import AccessPermission, Membership, Role
from apps.organizations.models import Branch, BusinessSection, Organization


PERMISSIONS = {
    "organization.view": "View organization settings",
    "organization.manage": "Update organization settings",
    "staff.manage": "Manage staff accounts and memberships",
    "roles.manage": "Manage organization roles and permissions",
    "dashboard.view": "View dashboard summaries",
    "sales.view": "View sales",
    "sales.create": "Create sales",
    "orders.view": "View department orders",
    "orders.create": "Create department orders",
    "orders.update": "Update department order workflow",
    "inventory.view": "View inventory",
    "inventory.adjust": "Adjust inventory",
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
    "expenses.manage": "Update draft expenses",
}

ROLE_PERMISSIONS = {
    "owner-admin": set(PERMISSIONS),
    "manager": {"organization.view", "dashboard.view", "sales.view", "sales.create", "orders.view", "orders.create", "orders.update", "inventory.view", "inventory.adjust", "reports.view", "customers.view", "customers.create", "customers.manage", "suppliers.view", "suppliers.create", "suppliers.manage", "catalog.view", "catalog.create", "catalog.manage", "expenses.view", "expenses.create", "expenses.manage"},
    "cashier": {"dashboard.view", "sales.view", "sales.create", "customers.view", "customers.create"},
    "department-staff": {"dashboard.view", "orders.view", "orders.create", "orders.update", "inventory.view"},
}


class Command(BaseCommand):
    help = "Create an initial organization, its business sections, branch, roles, and optional owner membership."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--admin-username", help="Existing Django username to grant owner-admin access")

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Organization name cannot be blank.")
        if Organization.objects.filter(name__iexact=name).exists():
            raise CommandError("An organization with that name already exists.")
        User = get_user_model()
        user = None
        if options["admin_username"]:
            try:
                user = User.objects.get(username=options["admin_username"])
            except User.DoesNotExist as exc:
                raise CommandError("Create the Django user first with `manage.py createsuperuser`.") from exc

        organization = Organization.objects.create(name=name)
        section_specs = [("Clothing", "clothing"), ("Printing", "printing"), ("Photography", "photography")]
        sections = [BusinessSection.objects.create(organization=organization, name=n, code=c) for n, c in section_specs]
        Branch.objects.create(organization=organization, name="Main Location", code="main", timezone=organization.timezone)
        permission_objects = {
            code: AccessPermission.objects.get_or_create(code=code, defaults={"description": description})[0]
            for code, description in PERMISSIONS.items()
        }
        roles = {}
        for code, codes in ROLE_PERMISSIONS.items():
            role, _ = Role.objects.get_or_create(organization=organization, code=code, defaults={
                "name": code.replace("-", " ").title(), "is_system": True,
            })
            role.permissions.set([permission_objects[p] for p in codes])
            roles[code] = role
        if user:
            membership = Membership.objects.create(
                user=user, organization=organization, role=roles["owner-admin"],
                all_sections=True, all_branches=True,
            )
            membership.sections.set(sections)
        self.stdout.write(self.style.SUCCESS(f"Created {organization.name} with 3 sections, 1 branch, and 4 roles."))
        if user:
            self.stdout.write(self.style.SUCCESS(f"Granted owner-admin access to {user.get_username()}."))
        else:
            self.stdout.write("No user was assigned. Run with --admin-username after creating a Django user.")
