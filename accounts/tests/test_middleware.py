from django.conf import settings
from django.utils import timezone

from accounts.middleware import UserTimeZoneMiddleware


class TestUserTimeZoneMiddleware:
    def test_call__activates_saved_time_zone(self, rf):
        request = rf.get("/")
        request.session = {"django_timezone": "America/New_York"}
        middleware = UserTimeZoneMiddleware(
            lambda request: timezone.get_current_timezone_name()
        )

        assert middleware(request) == "America/New_York"

    def test_call__deactivates_without_a_saved_time_zone(self, rf):
        request = rf.get("/")
        request.session = {}
        middleware = UserTimeZoneMiddleware(
            lambda request: timezone.get_current_timezone_name()
        )

        assert middleware(request) == settings.TIME_ZONE

    def test_call__falls_back_for_unknown_time_zone(self, rf):
        request = rf.get("/")
        request.session = {"django_timezone": "Mars/Olympus"}
        middleware = UserTimeZoneMiddleware(
            lambda request: timezone.get_current_timezone_name()
        )

        assert middleware(request) == settings.TIME_ZONE
