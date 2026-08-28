from django.contrib import admin

from accounts.admin import MembershipAdmin, OrganizationAdmin
from accounts.models import Membership, Organization


class TestOrganizationAdmin:
    def test_organization_admin__registered(self):
        assert isinstance(admin.site._registry[Organization], OrganizationAdmin)

    def test_organization_admin__list_display(self):
        assert "slug" in OrganizationAdmin.list_display
        assert "created_at" in OrganizationAdmin.list_display
        assert "suspended_at" in OrganizationAdmin.list_display

    def test_organization_admin__search_fields(self):
        assert "slug" in OrganizationAdmin.search_fields


class TestMembershipAdmin:
    def test_membership_admin__registered(self):
        assert isinstance(admin.site._registry[Membership], MembershipAdmin)

    def test_membership_admin__list_display(self):
        assert "org" in MembershipAdmin.list_display
        assert "user" in MembershipAdmin.list_display
        assert "role" in MembershipAdmin.list_display
