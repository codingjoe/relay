import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.admin import MembershipAdmin, OrganizationAdmin
from accounts.models import Membership, Organization


class TestOrganizationAdmin:
    def test_organization_admin__registered(self):
        assert isinstance(admin.site._registry[Organization], OrganizationAdmin)

    def test_organization_admin__list_display(self):
        assert "slug" in OrganizationAdmin.list_display
        assert "created_at" in OrganizationAdmin.list_display

    def test_organization_admin__search_fields(self):
        assert "slug" in OrganizationAdmin.search_fields


class TestMembershipAdmin:
    def test_membership_admin__registered(self):
        assert isinstance(admin.site._registry[Membership], MembershipAdmin)

    def test_membership_admin__list_display(self):
        assert "org" in MembershipAdmin.list_display
        assert "user" in MembershipAdmin.list_display
        assert "role" in MembershipAdmin.list_display


@pytest.mark.django_db
class TestOrganizationAdminUnlockReputation:
    def test_post__clears_reputation_lock(self, client, org):
        org.reputation_locked = True
        org.reputation_locked_at = timezone.now()
        org.save(
            update_fields=["reputation_locked", "reputation_locked_at", "modified_at"]
        )
        admin_user = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        client.force_login(admin_user)

        response = client.post(
            reverse("admin:accounts_organization_changelist"),
            {"action": "unlock_reputation", "_selected_action": str(org.pk)},
        )

        assert response.status_code == 302
        org.refresh_from_db()
        assert not org.reputation_locked
        assert org.reputation_locked_at is None
