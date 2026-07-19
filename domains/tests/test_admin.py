from django.contrib import admin

from domains.admin import DomainAdmin
from domains.models import Domain


class TestDomainAdmin:
    def test_domain_admin__registered(self):
        assert isinstance(admin.site._registry[Domain], DomainAdmin)

    def test_domain_admin__list_display(self):
        assert "name" in DomainAdmin.list_display
        assert "org" in DomainAdmin.list_display
        assert "verified_at" in DomainAdmin.list_display
        assert "nameserver_status" in DomainAdmin.list_display

    def test_domain_admin__search_fields(self):
        assert "name" in DomainAdmin.search_fields
        assert "org__name" in DomainAdmin.search_fields

    def test_domain_admin__readonly_verification_token(self):
        assert "verification_token" in DomainAdmin.readonly_fields
