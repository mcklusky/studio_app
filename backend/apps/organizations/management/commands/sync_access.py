from django.core.management.base import BaseCommand

from apps.identity.access import sync_system_roles
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Apply the current permission catalog to every organization's system roles."

    def handle(self, *args, **options):
        for organization in Organization.objects.all():
            sync_system_roles(organization)
            self.stdout.write(f"Synced roles for {organization.name}.")
