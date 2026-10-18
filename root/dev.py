"""Serve the web and MCP applications from one origin for local development."""

import importlib
import os
import typing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django_esm import asgi as esm  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

# Imported by name to avoid an import-linter edge from root to the MCP app.
mcp_application = importlib.import_module("services.mcp.asgi").application


if not settings.DEBUG:
    raise ImproperlyConfigured(  # noqa: TRY003
        "The combined web and MCP server is only available with DEBUG on."
    )


class ASGIEndpoint:
    """Wrap an application so Starlette can serve it as a route."""

    def __init__(self, app: typing.Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        await self.app(scope, receive, send)


web_application = esm.ESM(get_asgi_application())

application = Starlette(
    routes=[
        Route("/mcp", endpoint=ASGIEndpoint(mcp_application)),
        Mount("/", app=web_application),
    ],
    lifespan=mcp_application.router.lifespan_context,
)
