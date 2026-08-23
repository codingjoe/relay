import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from accounts.context_processors import organizations


class TestOrganizationsContextProcessor:
    @pytest.mark.django_db
    def test_organizations__authenticated_user(self, user, org):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.current_org = org
        context = organizations(request)
        assert "user_orgs" in context
        assert "current_org" in context
        assert context["current_org"] == org
        assert org in context["user_orgs"]

    @pytest.mark.django_db
    def test_organizations__no_current_org(self, user):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        assert organizations(request) == {}

    def test_organizations__unauthenticated_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()
        assert organizations(request) == {}

    def test_organizations__missing_user_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        assert organizations(request) == {}
