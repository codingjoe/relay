import pytest
from django.http import Http404
from django.urls import reverse

from alternative_to.views import AlternativeToDetailView, AlternativeToListView


class TestListComparisons:
    def test_list_comparisons__returns_sorted_articles(self):
        articles = AlternativeToListView.get_articles()
        slugs = [a["slug"] for a in articles]
        assert slugs == sorted(slugs)
        assert "ses" in slugs
        assert "sendgrid" in slugs
        assert "mailgun" in slugs
        assert "brevo" in slugs
        assert "mailjet" in slugs
        assert "mailchimp" in slugs

    def test_list_comparisons__each_has_title(self):
        articles = AlternativeToListView.get_articles()
        for article in articles:
            assert article["title"]
            assert article["slug"]

    def test_list_comparisons__includes_description(self):
        articles = AlternativeToListView.get_articles()
        ses = next(a for a in articles if a["slug"] == "ses")
        assert ses["description"]


class TestComparisonPath:
    def test_comparison_path__resolves_existing_slug(self):
        path = AlternativeToDetailView.get_article_path("ses")
        assert path.exists()

    def test_comparison_path__raises_404_for_missing_slug(self):
        with pytest.raises(Http404):
            AlternativeToDetailView.get_article_path("nonexistent")


class TestAlternativeToListView:
    def test_get__renders_list(self, client):
        response = client.get(reverse("alternative_to:list"))
        assert response.status_code == 200
        assert "articles" in response.context
        assert len(response.context["articles"]) > 0


class TestAlternativeToDetailView:
    def test_get__renders_article(self, client):
        response = client.get(reverse("alternative_to:detail", args=["ses"]))
        assert response.status_code == 200
        assert "markdown_template" in response.context
        assert response.context["markdown_template"] == "ses.md"

    def test_get__not_found(self, client):
        response = client.get(reverse("alternative_to:detail", args=["nonexistent"]))
        assert response.status_code == 404

    def test_get_title__returns_article_title(self, rf):
        request = rf.get("/alternative-to/ses/")
        request.resolver_match = type(
            "Match",
            (),
            {"kwargs": {"slug": "ses"}},
        )()
        assert AlternativeToDetailView.get_title(request) == "Alternative to Amazon SES"

    def test_get__returns_markdown_when_accept_header(self, client):
        response = client.get(
            reverse("alternative_to:detail", args=["ses"]),
            HTTP_ACCEPT="text/markdown",
        )
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# Alternative to Amazon SES" in body
        assert "Quick comparison" in body

    def test_get__returns_markdown_with_url_param(self, client):
        response = client.get(reverse("alternative_to:detail", args=["ses"]) + "?md=1")
        assert response.status_code == 200
        assert "text/markdown" in response["Content-Type"]
        body = response.content.decode()
        assert "# Alternative to Amazon SES" in body

    def test_get__returns_html_for_browser_request(self, client):
        response = client.get(reverse("alternative_to:detail", args=["ses"]))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_get__html_omits_license(self, client):
        response = client.get(reverse("alternative_to:detail", args=["ses"]))
        body = response.content.decode()
        assert "Creative Commons" not in body

    def test_get__markdown_omits_license(self, client):
        response = client.get(
            reverse("alternative_to:detail", args=["ses"]),
            HTTP_ACCEPT="text/markdown",
        )
        body = response.content.decode()
        assert "CC-BY-SA" not in body
