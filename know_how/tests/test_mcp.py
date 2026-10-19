import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from know_how.mcp import get_know_how_article, register_know_how_resources
from know_how.views import KnowHowListView


class TestRegisterResources:
    def test_register_know_how_resources__registers_one_resource_per_article(self):
        mcp = FastMCP(name="test")

        register_know_how_resources(mcp)

        assert len(list(KnowHowListView.get_articles())) > 0


class TestGetKnowHowArticle:
    def test_get_know_how_article__returns_rendered_markdown(self):
        article = get_know_how_article("dmarc")

        assert "# DMARC" in article
        assert "{% url" not in article
        assert "Creative Commons" in article

    def test_get_know_how_article__rejects_unknown_slug(self):
        with pytest.raises(ResourceError):
            get_know_how_article("unknown")
