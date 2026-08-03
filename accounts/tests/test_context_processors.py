import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from accounts.context_processors import organizations


@pytest.mark.django_db
class TestOrganizationsContextProcessor:
    def test_organizations__authenticated_user(self, user, org):
        factory = RequestFactory()
        request = factory.get("/")
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "session"
        request.user = user
        request.current_org = org
        context = organizations(request)
        assert "user_orgs" in context
        assert "current_org" in context
        assert context["current_org"] == org
        assert org in context["user_orgs"]

    def test_organizations__no_current_org(self, user):
        factory = RequestFactory()
        request = factory.get("/")
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "session"
        request.user = user
        context = organizations(request)
        assert context["current_org"] is None

    def test_organizations__unauthenticated_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()
        assert organizations(request) == {}

    def test_organizations__no_user_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        assert organizations(request) == {}

    def test_organizations__no_session_cookie_returns_empty(self, user):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        assert organizations(request) == {}
