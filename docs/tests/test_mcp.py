from fastmcp.server.providers import LocalProvider

from docs.content import DocsContent
from docs.mcp import get_docs_article, register_components


class TestRegisterComponents:
    async def test_register_components__registers_one_resource_per_article(self):
        provider = LocalProvider()

        register_components(provider)

        resources = await provider.list_resources()
        assert {str(resource.uri) for resource in resources} == {
            f"docs://{slug}" for slug, _ in DocsContent.get_articles()
        }


class TestGetDocsArticle:
    def test_get_docs_article__returns_rendered_markdown(self):
        article = get_docs_article("security")

        assert "# Security" in article
        assert "{% url" not in article
        assert not article.startswith("---")
