from django.urls import reverse

from knowhow.views import (
    KnowHowDetailView,
    extract_title,
    list_articles,
    parse_frontmatter,
)


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

    def test_extract_title__ignores_frontmatter(self):
        markdown_text = "---\nname: DMARC\n---\n\n# DMARC\n\nContent."
        assert extract_title(markdown_text) == "DMARC"


class TestParseFrontmatter:
    def test_parse_frontmatter__returns_metadata_and_content(self):
        text = "---\nname: DMARC\ndescription: Test\n---\n\n# DMARC\n\nBody."
        metadata, content = parse_frontmatter(text)
        assert metadata == {"name": "DMARC", "description": "Test"}
        assert content == "# DMARC\n\nBody."

    def test_parse_frontmatter__no_frontmatter(self):
        text = "# DMARC\n\nBody."
        metadata, content = parse_frontmatter(text)
        assert metadata == {}
        assert content == text


class TestKnowHowListView:
    def test_get__renders_list(self, client):
        response = client.get(reverse("knowhow:list"))
        assert response.status_code == 200
        assert "articles" in response.context
        assert len(response.context["articles"]) > 0


class TestKnowHowDetailView:
    def test_get__renders_article(self, client):
        response = client.get(reverse("knowhow:detail", args=["dmarc"]))
        assert response.status_code == 200
        assert "markdown_template" in response.context
        assert response.context["markdown_template"] == "dmarc.md"

    def test_get__not_found(self, client):
        response = client.get(reverse("knowhow:detail", args=["nonexistent"]))
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
            reverse("knowhow:detail", args=["dmarc"]),
            HTTP_ACCEPT="text/markdown",
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# DMARC" in body
        assert "TL;DR" in body

    def test_get__returns_markdown_with_url_param(self, client):
        response = client.get(reverse("knowhow:detail", args=["dmarc"]) + "?md=1")
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# DMARC" in body

    def test_get__returns_html_without_accept_header(self, client):
        response = client.get(reverse("knowhow:detail", args=["dmarc"]))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_get__html_includes_license(self, client):
        response = client.get(reverse("knowhow:detail", args=["dmarc"]))
        body = response.content.decode()
        assert "Creative Commons" in body
        assert "by-sa/4.0" in body

    def test_get__markdown_includes_license(self, client):
        response = client.get(
            reverse("knowhow:detail", args=["dmarc"]),
            HTTP_ACCEPT="text/markdown",
        )
        body = response.content.decode()
        assert "CC-BY-SA 4.0" in body
        assert "creativecommons.org/licenses/by-sa/4.0/" in body

    def test_get__markdown_includes_frontmatter(self, client):
        response = client.get(
            reverse("knowhow:detail", args=["dmarc"]),
            HTTP_ACCEPT="text/markdown",
        )
        body = response.content.decode()
        assert body.startswith("---\n")

    def test_get__markdown_frontmatter_has_metadata_fields(self, client):
        response = client.get(
            reverse("knowhow:detail", args=["dmarc"]),
            HTTP_ACCEPT="text/markdown",
        )
        body = response.content.decode()
        assert "name:" in body
        assert "description:" in body
        assert "author:" in body
        assert "license:" in body

    def test_get__list_includes_license(self, client):
        response = client.get(reverse("knowhow:list"))
        body = response.content.decode()
        assert "Creative Commons" in body
        assert "by-sa/4.0" in body
