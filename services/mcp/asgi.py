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

from .bindings import bind  # noqa: E402
from .middleware import DjangoRequestSignalsMiddleware  # noqa: E402

token_verifier = JWTVerifier(
    audience=settings.MCP_RESOURCE_URL,
    jwks_uri=settings.MCP_OIDC_JWKS_URL,
    issuer=settings.MCP_OIDC_ISSUER_URL,
    required_scopes=list(MCP_REQUIRED_SCOPES),
)
auth_provider = RemoteAuthProvider(
    token_verifier=token_verifier,
    authorization_servers=[settings.MCP_OIDC_ISSUER_URL],
    base_url=settings.MCP_BASE_URL,
    resource_name="relay MCP",
    # Clients request what the challenge names, so components need more than the identity scope.
    challenge_scopes=list(scopes.supported()),
    scopes_supported=list(scopes.supported()),
)
mcp = FastMCP(
    name="relay",
    instructions=(
        "Use relay to view and send email messages. Read the relay documentation "
        "and know-how articles as resources."
    ),
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
