import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Customer
from apps.identity.models import Membership, Role
from apps.organizations.models import Organization
from apps.organizations.services import bootstrap_organization

DEMO_USERS = [
    # username, first, last, role, section codes (None = all)
    ("owner", "Demo", "Owner", "owner-admin", None),
    ("cashier", "Demo", "Cashier", "cashier", None),
    ("printer", "Demo", "Printer", "department-staff", ["printing"]),
]


class Command(BaseCommand):
    help = "LOCAL DEVELOPMENT ONLY: create a demo workspace with one user per starter role."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Demo Studio")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=true.")
        if Organization.objects.filter(name__iexact=options["name"]).exists():
            raise CommandError(f"{options['name']} already exists.")
        User = get_user_model()
        clashes = [u for u, *_ in DEMO_USERS if User.objects.filter(username=u).exists()]
        if clashes:
            raise CommandError(f"Users already exist: {', '.join(clashes)}")

        organization = bootstrap_organization(options["name"])
        credentials = []
        for username, first, last, role_code, section_codes in DEMO_USERS:
            password = secrets.token_urlsafe(9)
            user = User.objects.create_user(username=username, password=password, first_name=first, last_name=last)
            membership = Membership.objects.create(
                user=user,
                organization=organization,
                role=Role.objects.get(organization=organization, code=role_code),
                all_sections=section_codes is None,
                all_branches=True,
            )
            if section_codes:
                membership.sections.set(organization.sections.filter(code__in=section_codes))
            credentials.append((username, role_code, password))

        for name, phone in [("Amara Sesay", "+231 770 000 001"), ("James Morris", "+231 880 000 002"), ("Peter Kpoto", "")]:
            Customer.objects.create(organization=organization, name=name, phone=phone)

        self.stdout.write(self.style.SUCCESS(f"Created {organization.name}. Sign-in details (shown once):"))
        for username, role_code, password in credentials:
            self.stdout.write(f"  {username:<9} {role_code:<17} {password}")
