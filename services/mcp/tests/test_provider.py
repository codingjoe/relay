from services.mcp.provider import AppMCPProvider


class TestAppMCPModules:
    def test_app_mcp_modules__imports_component_modules(self):
        modules = list(AppMCPProvider.app_mcp_modules())

        assert {
            "docs.mcp",
            "know_how.mcp",
            "services.email.message.mcp",
        } <= {module.__name__ for module in modules}


class TestAppMCPProvider:
    async def test_app_mcp_provider__registers_tools_and_resources(self):
        provider = AppMCPProvider()

        tools = await provider.list_tools()
        resources = await provider.list_resources()
        templates = await provider.list_resource_templates()

        assert {"list_messages"} <= {tool.name for tool in tools}
        assert "email://messages/{message_id}" in {
            template.uri_template for template in templates
        }
        assert {"docs://security", "know-how://dmarc"} <= {
            str(resource.uri) for resource in resources
        }
