from django.urls import reverse

from know_how.views import KnowHowDetailView, extract_title, list_articles


class TestListArticles:
    def test_list_articles__returns_sorted_articles(self):
        articles = list_articles()
        slugs = [a["slug"] for a in articles]
        assert slugs == sorted(slugs)
        assert "dmarc" in slugs
        assert "spf" in slugs

    def test_list_articles__each_has_title(self):
        articles = list_articles()
        for article in articles:
            assert article["title"]
            assert article["slug"]


class TestExtractTitle:
    def test_extract_title__returns_h1_text(self):
        markdown_text = "# DMARC\n\nSome content."
        assert extract_title(markdown_text) == "DMARC"

    def test_extract_title__returns_empty_for_no_h1(self):
        markdown_text = "Some content without a heading."
        assert extract_title(markdown_text) == ""


class TestKnowHowListView:
    def test_get__renders_list(self, client):
        response = client.get(reverse("know_how:list"))
        assert response.status_code == 200
        assert "articles" in response.context
        assert len(response.context["articles"]) > 0


class TestKnowHowDetailView:
    def test_get__renders_article(self, client):
        response = client.get(reverse("know_how:detail", args=["dmarc"]))
        assert response.status_code == 200
        assert "markdown_template" in response.context
        assert response.context["markdown_template"] == "dmarc.md"

    def test_get__not_found(self, client):
        response = client.get(reverse("know_how:detail", args=["nonexistent"]))
        assert response.status_code == 404

    def test_get_title__returns_article_title(self, rf):
        request = rf.get("/know-how/dmarc/")
        request.resolver_match = type(
            "Match",
            (),
            {"kwargs": {"slug": "dmarc"}},
        )()
        assert KnowHowDetailView.get_title(request) == "DMARC"

    def test_get__returns_markdown_when_accept_header(self, client):
        response = client.get(
            reverse("know_how:detail", args=["dmarc"]),
            HTTP_ACCEPT="text/markdown",
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# DMARC" in body
        assert "TL;DR" in body

    def test_get__returns_html_without_accept_header(self, client):
        response = client.get(reverse("know_how:detail", args=["dmarc"]))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]
