import pathlib

from django.urls import reverse

from alternative_to.views import ALTERNATIVE_TO_DIR
from docs.views import DOCS_DIR, SLUGS, DocsDetailView, DocsListView
from know_how.views import KNOW_HOW_DIR

LEGAL_SLUGS = frozenset({"imprint", "terms", "privacy"})


class TestSlugUniqueness:
    def test_slugs__unique_across_markdown_apps(self):
        """The template loader resolves markdown by filename across all DIRS.

        Markdown template DIRS are flat, so a slug that exists in two apps
        renders the wrong file. See abstract.views.MarkdownArticleMixin.
        """

        other_slugs = (
            {p.stem for p in pathlib.Path(ALTERNATIVE_TO_DIR).glob("*.md")}
            | {p.stem for p in pathlib.Path(KNOW_HOW_DIR).glob("*.md")}
            | LEGAL_SLUGS
        )
        assert not SLUGS & other_slugs
        assert pathlib.Path(DOCS_DIR).glob("*.md")


class TestListArticles:
    def test_list_articles__returns_sorted_articles(self):
        slugs = [slug for slug, _ in DocsListView.get_articles()]
        assert slugs == sorted(slugs)
        assert "security" in slugs
        assert "deliverability" in slugs

    def test_list_articles__each_has_title_and_description(self):
        for slug, metadata in DocsListView.get_articles():
            assert metadata["name"]
            assert metadata.get("description")
            assert metadata["author"]
            assert slug


class TestDocsListView:
    def test_get__renders_list(self, client):
        response = client.get(reverse("docs:list"))
        assert response.status_code == 200
        assert "articles" in response.context
        assert len(response.context["articles"]) == 6


class TestDocsDetailView:
    def test_get__renders_article(self, client):
        response = client.get(reverse("docs:detail", args=["security"]))
        assert response.status_code == 200
        assert "markdown_template" in response.context
        assert response.context["markdown_template"] == "security.md"

    def test_get__not_found(self, client):
        response = client.get(reverse("docs:detail", args=["nonexistent"]))
        assert response.status_code == 404

    def test_get_title__returns_article_title(self, rf):
        request = rf.get("/docs/security/")
        request.resolver_match = type(
            "Match",
            (),
            {"kwargs": {"slug": "security"}},
        )()
        assert DocsDetailView.get_title(request) == "Security"

    def test_get__includes_meta_description(self, client):
        response = client.get(reverse("docs:detail", args=["security"]))
        assert response.context["meta_description"]
        assert "meta_description" in response.context

    def test_get__returns_markdown_when_accept_header(self, client):
        response = client.get(
            reverse("docs:detail", args=["security"]),
            HTTP_ACCEPT="text/markdown",
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# Security" in body
        assert "TL;DR" in body

    def test_get__returns_markdown_with_url_param(self, client):
        response = client.get(reverse("docs:detail", args=["security"]) + "?md=1")
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# Security" in body

    def test_get__returns_html_without_accept_header(self, client):
        response = client.get(reverse("docs:detail", args=["security"]))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_get__markdown_strips_frontmatter(self, client):
        response = client.get(
            reverse("docs:detail", args=["security"]),
            HTTP_ACCEPT="text/markdown",
        )
        body = response.content.decode()
        assert not body.startswith("---\n")
        assert "name:" not in body
