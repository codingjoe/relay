import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from docs.mcp import get_docs_article, register_docs_resources
from docs.views import DocsListView


class TestRegisterResources:
    def test_register_docs_resources__registers_one_resource_per_article(self):
        mcp = FastMCP(name="test")

        register_docs_resources(mcp)

        assert len(list(DocsListView.get_articles())) > 0


class TestGetDocsArticle:
    def test_get_docs_article__returns_rendered_markdown(self):
        article = get_docs_article("security")

        assert "# Security" in article
        assert "{% url" not in article
        assert not article.startswith("---")

    def test_get_docs_article__rejects_unknown_slug(self):
        with pytest.raises(ResourceError):
            get_docs_article("unknown")
