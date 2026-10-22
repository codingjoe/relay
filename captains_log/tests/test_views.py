import pytest
from django.http import Http404
from django.urls import reverse

from captains_log.content import CaptainsLogContent
from captains_log.views import CaptainsLogDetailView, CaptainsLogImageView


class TestListArticles:
    def test_list_articles__returns_newest_first(self):
        articles = list(CaptainsLogContent.get_articles())
        dates = [metadata["date"] for _, metadata in articles]
        assert dates == sorted(dates, reverse=True)
        assert articles[0][0] == "2026-10"

    def test_list_articles__each_has_title_date_and_description(self):
        for slug, metadata in CaptainsLogContent.get_articles():
            assert metadata["name"]
            assert metadata.get("date")
            assert metadata.get("description")
            assert slug


class TestCaptainsLogListView:
    def test_get__renders_list(self, client):
        response = client.get(reverse("captains_log:list"))
        assert response.status_code == 200
        assert "articles" in response.context
        assert response.context["articles"][0]["slug"] == "2026-10"


class TestCaptainsLogDetailView:
    def test_get__renders_update(self, client):
        response = client.get(reverse("captains_log:detail", args=["2026-10"]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Captain&rsquo;s log, stardate 2026.294" in content
        assert 'src="/captains-log/2026-10/images/mcp.png"' in content
        assert (
            '<meta property="og:image" '
            'content="http://testserver/captains-log/2026-10/images/mcp.png">'
        ) in content
        assert '<meta property="og:image:width" content="1280">' in content
        assert '<meta property="og:image:height" content="640">' in content
        assert (
            '<meta name="twitter:image" '
            'content="http://testserver/captains-log/2026-10/images/mcp.png">'
        ) in content

    def test_get__not_found(self, client):
        response = client.get(reverse("captains_log:detail", args=["nonexistent"]))
        assert response.status_code == 404

    def test_get_title__returns_update_title(self, rf):
        request = rf.get("/captains-log/2026-10/")
        request.resolver_match = type(
            "Match",
            (),
            {"kwargs": {"slug": "2026-10"}},
        )()
        assert CaptainsLogDetailView.get_title(request) == "October 2026"

    def test_get__returns_markdown_when_accept_header(self, client):
        response = client.get(
            reverse("captains_log:detail", args=["2026-10"]),
            HTTP_ACCEPT="text/markdown",
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# Captain's log, stardate 2026.294" in body
        assert "images/mcp.png" in body
        assert not body.startswith("---\n")

    def test_get__returns_markdown_with_url_param(self, client):
        response = client.get(
            reverse("captains_log:detail", args=["2026-10"]) + "?md=1"
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]


class TestCaptainsLogImageView:
    def test_get__serves_the_update_screenshot(self, client):
        response = client.get(
            reverse("captains_log:image", args=["2026-10", "mcp.png"])
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"

    def test_get__rejects_unknown_slug(self, client):
        response = client.get("/captains-log/1999-01/images/mcp.png")
        assert response.status_code == 404

    def test_get__rejects_missing_image(self, client):
        response = client.get(
            reverse("captains_log:image", args=["2026-10", "nope.png"])
        )
        assert response.status_code == 404

    def test_get__rejects_traversal(self, rf):
        request = rf.get("/captains-log/2026-10/images/../2026-10.md")
        with pytest.raises(Http404):
            CaptainsLogImageView.as_view()(
                request,
                slug="2026-10",
                name="../2026-10.md",
            )
