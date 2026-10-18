import json

import pytest
from fastmcp.exceptions import ResourceError

from know_how.mcp import get_know_how_article, list_know_how


class TestListKnowHow:
    def test_list_know_how__returns_every_article(self):
        articles = json.loads(list_know_how())["articles"]

        assert articles
        assert [article["slug"] for article in articles] == sorted(
            article["slug"] for article in articles
        )
        assert "dmarc" in {article["slug"] for article in articles}
        assert all(article["author"] for article in articles)
        assert all(
            article["uri"] == f"relay://know-how/{article['slug']}"
            for article in articles
        )


class TestGetKnowHowArticle:
    def test_get_know_how_article__returns_rendered_markdown(self):
        article = get_know_how_article("dmarc")

        assert "# DMARC" in article
        assert "{% url" not in article
        assert "Creative Commons" in article

    def test_get_know_how_article__rejects_unknown_slug(self):
        with pytest.raises(ResourceError):
            get_know_how_article("unknown")
