from fastmcp.server.providers import LocalProvider

from know_how.content import KnowHowContent
from know_how.mcp import get_know_how_article, register_components


class TestRegisterComponents:
    async def test_register_components__registers_one_resource_per_article(self):
        provider = LocalProvider()

        register_components(provider)

        resources = await provider.list_resources()
        assert {str(resource.uri) for resource in resources} == {
            f"know-how://{slug}" for slug, _ in KnowHowContent.get_articles()
        }


class TestGetKnowHowArticle:
    def test_get_know_how_article__returns_rendered_markdown(self):
        article = get_know_how_article("dmarc")

        assert "# DMARC" in article
        assert "{% url" not in article
        assert "Creative Commons" in article
