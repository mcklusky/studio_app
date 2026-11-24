from django.db import transaction

from apps.identity.access import sync_system_roles
from apps.identity.models import Membership
from apps.organizations.models import Branch, BusinessSection, Organization

DEFAULT_SECTIONS = [("Clothing", "clothing"), ("Printing", "printing"), ("Photography", "photography")]


@transaction.atomic
def bootstrap_organization(name, owner=None):
    """Create an organization with the three business sections, a main branch,
    the starter roles, and (optionally) an owner-admin membership."""
    organization = Organization.objects.create(name=name)
    sections = [BusinessSection.objects.create(organization=organization, name=n, code=c) for n, c in DEFAULT_SECTIONS]
    Branch.objects.create(organization=organization, name="Main Location", code="main", timezone=organization.timezone)
    roles = sync_system_roles(organization)
    if owner is not None:
        membership = Membership.objects.create(
            user=owner, organization=organization, role=roles["owner-admin"], all_sections=True, all_branches=True
        )
        membership.sections.set(sections)
    return organization
