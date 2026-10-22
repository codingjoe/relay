from django.templatetags.static import static
from django.urls import reverse

from captains_log.content import CaptainsLogContent
from captains_log.views import CaptainsLogDetailView


class TestListArticles:
    def test_list_articles__returns_newest_first(self):
        articles = list(CaptainsLogContent.get_articles())
        dates = [metadata["date"] for _, metadata in articles]
        assert dates == sorted(dates, reverse=True)
        assert articles[0][0] == "2026-10"

    def test_list_articles__orders_two_logs_newest_first(self, tmp_path, monkeypatch):
        (tmp_path / "2026-09.md").write_text(
            "---\nname: September 2026\ndate: 2026-09-01\n---\n",
            encoding="utf-8",
        )
        (tmp_path / "2026-10.md").write_text(
            "---\nname: October 2026\ndate: 2026-10-01\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(CaptainsLogContent, "docs_dir", tmp_path)
        monkeypatch.setattr(
            CaptainsLogContent,
            "slugs",
            frozenset({"2026-09", "2026-10"}),
        )

        articles = list(CaptainsLogContent.get_articles())

        assert [slug for slug, _ in articles] == ["2026-10", "2026-09"]

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
        assert "relay station log, stardate 2026.294" in content
        image_url = static("captains_log/2026-10/mcp.png")
        assert f'src="{image_url}"' in content
        assert (
            f'<meta property="og:image" content="http://testserver{image_url}">'
        ) in content
        assert '<meta property="og:image:width" content="1280">' in content
        assert '<meta property="og:image:height" content="640">' in content
        assert (
            f'<meta name="twitter:image" content="http://testserver{image_url}">'
        ) in content

    def test_get__not_found(self, client):
        response = client.get(reverse("captains_log:detail", args=["nonexistent"]))
        assert response.status_code == 404

    def test_get_title__returns_update_title(self, rf):
        request = rf.get("/station-log/2026-10/")
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
        assert "# relay station log, stardate 2026.294" in body
        assert "{% static 'captains_log/2026-10/mcp.png' %}" in body
        assert not body.startswith("---\n")

    def test_get__returns_markdown_with_url_param(self, client):
        response = client.get(
            reverse("captains_log:detail", args=["2026-10"]) + "?md=1"
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]


class TestRenderBody:
    def test_render_body__drops_the_markdown_line_breaks(self):
        html = str(CaptainsLogContent.render_body("2026-10"))

        assert "<br" not in html
        assert "The wormhole is quiet. The relay is not." in html
        assert static("captains_log/2026-10/mcp.png") in html
