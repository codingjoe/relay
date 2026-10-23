import zoneinfo
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.utils import timezone

from accounts.middleware import UserTimeZoneMiddleware
from accounts.models import UserPreference


class UntouchableUser:
    @property
    def is_authenticated(self):
        raise AssertionError


def build_request(rf, *, accessed=False, user=None):
    request = rf.get("/")
    request.session = SimpleNamespace(accessed=accessed)
    request.user = user
    return request


@pytest.fixture(autouse=True)
def reset_timezone():
    timezone.deactivate()
    yield
    timezone.deactivate()


class TestUserTimeZoneMiddleware:
    @pytest.mark.django_db
    def test_process_template_response__activates_saved_time_zone(self, rf, user):
        UserPreference.objects.create(user=user, time_zone="America/New_York")
        request = build_request(rf, accessed=True, user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_template_response(request, HttpResponse())

        assert timezone.get_current_timezone_name() == "America/New_York"

    @pytest.mark.django_db
    def test_process_template_response__deactivates_without_a_preference(
        self, rf, user
    ):
        request = build_request(rf, accessed=True, user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_template_response(request, HttpResponse())

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_process_template_response__skips_an_untouched_session(self, rf):
        request = build_request(rf, accessed=False, user=UntouchableUser())
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_template_response(request, HttpResponse())

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_process_template_response__skips_an_anonymous_user(self, rf):
        request = build_request(rf, accessed=True, user=AnonymousUser())
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_template_response(request, HttpResponse())

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    @pytest.mark.django_db
    def test_process_template_response__falls_back_for_unknown_time_zone(
        self, rf, user
    ):
        UserPreference.objects.create(user=user, time_zone="Mars/Olympus")
        request = build_request(rf, accessed=True, user=user)
        middleware = UserTimeZoneMiddleware(lambda request: HttpResponse())

        middleware.process_template_response(request, HttpResponse())

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE

    def test_call__deactivates_after_the_response(self, rf):
        request = build_request(rf)
        middleware = UserTimeZoneMiddleware(
            lambda request: timezone.activate(zoneinfo.ZoneInfo("UTC"))
        )

        middleware(request)

        assert timezone.get_current_timezone_name() == settings.TIME_ZONE
