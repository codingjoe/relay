"""Serve the web and MCP applications from one origin for local development."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django_esm import asgi as esm  # noqa: E402
from starlette.types import ASGIApp, Receive, Scope, Send  # noqa: E402

from .asgi import application as mcp_application  # noqa: E402


class DevelopmentOnlyError(ImproperlyConfigured):
    """Signal that the combined server was loaded outside development."""

    def __init__(self) -> None:
        super().__init__(
            "The combined web and MCP server is only available with DEBUG on."
        )


if not settings.DEBUG:
    raise DevelopmentOnlyError


class CombinedApplication:
    """
    Serve the web application and the MCP application from one origin.

    A Starlette mount compiles to `/mcp/{path:path}`, which never matches the
    endpoint itself, so the path the deployment routes is checked here instead.
    """

    def __init__(self) -> None:
        self.web: ASGIApp = esm.ESM(get_asgi_application())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            # Only the MCP application holds resources to start and stop.
            await mcp_application(scope, receive, send)
            return
        if scope["type"] == "http" and (
            scope["path"] == "/mcp" or scope["path"].startswith("/mcp/")
        ):
            await mcp_application(scope, receive, send)
            return
        await self.web(scope, receive, send)


application = CombinedApplication()
