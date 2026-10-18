import json

from django.conf import settings
from django.views import generic

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView


class SetupView(OrganizationScopedView, NoStoreCacheMixin, generic.TemplateView):
    """Walk a person through connecting an MCP client."""

    template_name = "mcp/setup.html"
    title = "MCP"
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        endpoint = settings.MCP_RESOURCE_URL
        return super().get_context_data(**kwargs) | {
            "endpoint": endpoint,
            "codex_command": f"codex mcp add relay --url {endpoint}",
            "client_config": json.dumps(
                {"mcpServers": {"relay": {"url": endpoint}}}, indent=2
            ),
        }
