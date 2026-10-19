from fastmcp import FastMCP

from docs.content import DocsContent
from docs.mcp import get_docs_article, register_docs_resources


class TestRegisterResources:
    async def test_register_docs_resources__registers_one_resource_per_article(self):
        mcp = FastMCP(name="test")

        register_docs_resources(mcp)

        resources = await mcp.list_resources()
        assert {str(resource.uri) for resource in resources} == {
            f"docs://{slug}" for slug, _ in DocsContent.get_articles()
        }


class TestGetDocsArticle:
    def test_get_docs_article__returns_rendered_markdown(self):
        article = get_docs_article("security")

        assert "# Security" in article
        assert "{% url" not in article
        assert not article.startswith("---")
