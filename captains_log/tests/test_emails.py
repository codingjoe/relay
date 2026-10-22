import pytest
from django.templatetags.static import static
from django_letter.notifications import registry

from captains_log.content import CaptainsLogContent
from captains_log.emails import (
    StationLogEmail,
    station_log_notification,
)

SLUG = "2026-10"


@pytest.fixture
def metadata():
    return CaptainsLogContent.get_article_metadata(SLUG)


def render(metadata):
    email = StationLogEmail(slug=SLUG, metadata=metadata, language="en-us")
    email.render()
    return email


class TestStationLogEmail:
    def test_get_subject__names_the_log(self, metadata):
        assert render(metadata).subject == "A new station log: October 2026"

    def test_render__includes_the_whole_log(self, metadata):
        html = render(metadata).html
        assert "relay station log, stardate 2026.294" in html
        assert "The holosuite run" in html
        assert "A new channel opens" in html
        assert "Supplemental log" in html
        assert "relay station out." in html

    def test_render__keeps_every_screenshot(self, metadata):
        html = render(metadata).html
        for image in (
            "sandbox-credential",
            "weekly-digest",
            "message-preview",
            "mcp",
            "get-started",
        ):
            assert static(f"captains_log/2026-10/{image}.png") in html
        assert 'width="600"' in html

    def test_render__links_to_the_log(self, metadata):
        html = render(metadata).html
        assert "Open this log in your browser" in html
        assert "/station-log/2026-10/" in html

    @pytest.mark.django_db
    def test_message__sets_the_unsubscribe_headers(self, user, metadata):
        email = StationLogEmail.to_user(
            user,
            slug=SLUG,
            metadata=metadata,
            language="en-us",
        )
        message = email.message()
        assert "List-Unsubscribe" in message
        assert "List-Unsubscribe-Post" in message
        assert "station-log" in message["List-Unsubscribe"]

    def test_notification__is_registered(self):
        assert registry["station-log"] is station_log_notification
        assert station_log_notification.default

    def test_render_preview__uses_the_latest_log(self):
        email = StationLogEmail.render_preview()
        assert "October 2026" in email.html
