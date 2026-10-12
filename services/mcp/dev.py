"""Serve the web and MCP applications from one origin for local development."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

import django

django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402
from django_esm import asgi as esm  # noqa: E402
from starlette.types import Receive, Scope, Send  # noqa: E402

from .asgi import application as mcp_application  # noqa: E402

web_application = esm.ESM(get_asgi_application())

# The MCP app serves its own health route, so it never reaches Django's.
MCP_PATHS = ("/health", "/mcp")


async def application(scope: Scope, receive: Receive, send: Send) -> None:
    """Route MCP traffic to the MCP app and everything else to Django."""
    if scope["type"] == "lifespan":
        await mcp_application(scope, receive, send)
        return
    path = scope.get("path", "")
    if path in MCP_PATHS or path.startswith("/mcp/"):
        await mcp_application(scope, receive, send)
        return
    await web_application(scope, receive, send)
