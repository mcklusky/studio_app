from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.identity.models import Membership, Role
from apps.organizations.services import bootstrap_organization

PASSWORD = "correct-horse-battery-1"


def make_user(username, **extra):
    return get_user_model().objects.create_user(username=username, password=PASSWORD, **extra)


def make_org(name, owner_username=None):
    owner = make_user(owner_username) if owner_username else None
    return bootstrap_organization(name, owner=owner), owner


def add_member(organization, username, role_code, *, sections=None, all_sections=False, active=True):
    """Add a user with the given starter role; scope to section codes unless all_sections."""
    user = make_user(username)
    membership = Membership.objects.create(
        user=user,
        organization=organization,
        role=Role.objects.get(organization=organization, code=role_code),
        all_sections=all_sections,
        all_branches=True,
        active=active,
    )
    if sections:
        membership.sections.set(organization.sections.filter(code__in=sections))
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client
