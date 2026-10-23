import zoneinfo
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views import generic

from abstract.views import CacheControlMixin
from accounts.middleware import UserTimeZoneMiddleware
from accounts.models import UserPreference


class UntouchableUser:
    @property
    def is_authenticated(self):
        raise AssertionError


class PublicView(CacheControlMixin, generic.TemplateView):
    cache_control = {"public": True}


def build_request(rf, *, session_key=None, user=None):
    request = rf.get("/")
    request.session = SimpleNamespace(session_key=session_key)
    request.user = user
    return request


@pytest.fixture(autouse=True)
def reset_timezone():
    timezone.deactivate()
    yield
    timezone.deactivate()


class TestUserTimeZoneMiddleware:
    @pytest.mark.django_db
    def test_process_view__activates_saved_time_zone(self, rf, user):
        UserPreference.objects.create(user=user, time_zone="America/New_York")
        request = build_request(rf, session_key="session-key", user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_view(request, lambda request: None, (), {})

        assert timezone.get_current_timezone_name() == "America/New_York"

    @pytest.mark.django_db
    def test_process_view__deactivates_without_a_preference(self, rf, user):
        request = build_request(rf, session_key="session-key", user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_view(request, lambda request: None, (), {})

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_process_view__skips_user_without_a_session(self, rf):
        request = build_request(rf, user=UntouchableUser())
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_view(request, lambda request: None, (), {})

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_process_view__skips_user_for_public_views(self, rf):
        request = build_request(rf, session_key="session-key", user=UntouchableUser())
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_view(request, PublicView.as_view(), (), {})

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    @pytest.mark.django_db
    def test_process_view__falls_back_for_unknown_time_zone(self, rf, user):
        UserPreference.objects.create(user=user, time_zone="Mars/Olympus")
        request = build_request(rf, session_key="session-key", user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_view(request, lambda request: None, (), {})

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_call__deactivates_after_the_response(self, rf):
        request = build_request(rf)
        middleware = UserTimeZoneMiddleware(
            lambda request: timezone.activate(zoneinfo.ZoneInfo("UTC"))
        )

        middleware(request)

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE
