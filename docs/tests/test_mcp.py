import pytest
from fastmcp.exceptions import ResourceError

from docs.mcp import get_docs_article, list_docs


class TestListDocs:
    def test_list_docs__returns_every_article(self):
        articles = list_docs()

        assert articles
        assert [article["slug"] for article in articles] == sorted(
            article["slug"] for article in articles
        )
        assert "security" in {article["slug"] for article in articles}
        assert all(article["author"] for article in articles)
        assert all(
            article["uri"] == f"docs://{article['slug']}" for article in articles
        )


class TestGetDocsArticle:
    def test_get_docs_article__returns_rendered_markdown(self):
        article = get_docs_article("security")

        assert "# Security" in article
        assert "{% url" not in article
        assert not article.startswith("---")

    def test_get_docs_article__rejects_unknown_slug(self):
        with pytest.raises(ResourceError):
            get_docs_article("unknown")
