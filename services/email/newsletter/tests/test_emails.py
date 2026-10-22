import pytest
from django_letter.notifications import registry

from captains_log.content import CaptainsLogContent
from services.email.newsletter.emails import (
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

    def test_render__shows_the_description(self, metadata):
        assert metadata["description"] in render(metadata).html

    def test_render__uses_the_social_image(self, metadata):
        assert "/station-log/2026-10/images/mcp.png" in render(metadata).html

    def test_render__links_to_the_log(self, metadata):
        html = render(metadata).html
        assert "/station-log/2026-10/" in html
        assert "Read the station log" in html

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
