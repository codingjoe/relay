import pytest
from django.contrib.auth.models import User

from accounts.models import Membership, Organization
from accounts.pipelines import create_default_organization


@pytest.mark.django_db
class TestCreateDefaultOrganization:
    def test_create_default_organization__new_user(self):
        user = User.objects.create_user(username="newbie", email="n@example.com")
        create_default_organization(backend=None, user=user, response={}, is_new=True)
        org = Organization.objects.get(slug="newbie")
        assert Membership.objects.filter(
            org=org, user=user, role=Membership.Role.ADMIN
        ).exists()

    def test_create_default_organization__skips_existing_user(self):
        user = User.objects.create_user(username="oldie", email="o@example.com")
        create_default_organization(backend=None, user=user, response={}, is_new=True)
        create_default_organization(backend=None, user=user, response={}, is_new=False)
        assert Organization.objects.filter(slug="oldie").count() == 1

    def test_create_default_organization__not_new_skips(self):
        user = User.objects.create_user(username="skip", email="s@example.com")
        create_default_organization(backend=None, user=user, response={}, is_new=False)
        assert not Organization.objects.filter(slug="skip").exists()
