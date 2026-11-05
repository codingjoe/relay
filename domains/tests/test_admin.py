import pytest
from django.contrib import admin
from django.urls import reverse

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
        assert "org__slug" in DomainAdmin.search_fields

    @pytest.mark.django_db
    def test_domain_admin__changelist_search_by_org_slug(self, client, admin_user, org):
        domain = Domain.objects.create(name="example.com", org=org)
        client.force_login(admin_user)

        response = client.get(
            reverse("admin:domains_domain_changelist"),
            {"q": org.slug},
        )

        assert response.status_code == 200
        assert domain in response.context["cl"].result_list
