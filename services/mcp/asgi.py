import os

import django
from starlette.requests import Request
from starlette.responses import JSONResponse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

django.setup()

from django.conf import settings  # noqa: E402
from fastmcp import FastMCP  # noqa: E402
from fastmcp.server.auth import RemoteAuthProvider  # noqa: E402
from fastmcp.server.auth.providers.jwt import JWTVerifier  # noqa: E402

from abstract.scopes import MCP_REQUIRED_SCOPES, scopes  # noqa: E402

from .components import bind  # noqa: E402
from .middleware import DjangoRequestSignalsMiddleware  # noqa: E402


class RelayJWTVerifier(JWTVerifier):
    """Advertise the registered scopes as supported."""

    @property
    def scopes_supported(self) -> list[str]:
        return list(scopes.supported())


token_verifier = RelayJWTVerifier(
    audience=settings.RELAY_MCP_RESOURCE_URL,
    jwks_uri=settings.RELAY_MCP_OIDC_JWKS_URL,
    issuer=settings.RELAY_MCP_OIDC_ISSUER_URL,
    required_scopes=list(MCP_REQUIRED_SCOPES),
)
auth_provider = RemoteAuthProvider(
    token_verifier=token_verifier,
    authorization_servers=[settings.RELAY_MCP_OIDC_ISSUER_URL],
    base_url=settings.RELAY_MCP_BASE_URL,
    resource_name="relay MCP",
)
mcp = FastMCP(
    name="relay",
    instructions="Use relay to view email messages.",
    auth=auth_provider,
    list_page_size=50,
    mask_error_details=not settings.DEBUG,
    strict_input_validation=True,
)
mcp.add_middleware(DjangoRequestSignalsMiddleware())
bind(mcp)


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


application = mcp.http_app(
    path="/mcp",
    stateless_http=True,
    json_response=True,
    host_origin_protection=True,
    allowed_hosts=[*settings.ALLOWED_HOSTS, "localhost"],
)
