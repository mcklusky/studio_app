from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.organizations.services import bootstrap_organization


class Command(BaseCommand):
    help = "Create an initial organization, its business sections, branch, roles, and optional owner membership."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--admin-username", help="Existing Django username to grant owner-admin access")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Organization name cannot be blank.")
        if Organization.objects.filter(name__iexact=name).exists():
            raise CommandError("An organization with that name already exists.")
        user = None
        if options["admin_username"]:
            User = get_user_model()
            try:
                user = User.objects.get(username=options["admin_username"])
            except User.DoesNotExist as exc:
                raise CommandError("Create the Django user first with `manage.py createsuperuser`.") from exc

        organization = bootstrap_organization(name, owner=user)
        self.stdout.write(self.style.SUCCESS(f"Created {organization.name} with 3 sections, 1 branch, and 4 roles."))
        if user:
            self.stdout.write(self.style.SUCCESS(f"Granted owner-admin access to {user.get_username()}."))
        else:
            self.stdout.write("No user was assigned. Run with --admin-username after creating a Django user.")
