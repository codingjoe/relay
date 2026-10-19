import os

# Send FastMCP records to the project logger instead of its Rich console handler.
os.environ.setdefault("FASTMCP_LOG_ENABLED", "false")

import django
from starlette.requests import Request
from starlette.responses import JSONResponse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

django.setup()

from django.conf import settings  # noqa: E402
from fastmcp import FastMCP  # noqa: E402
from fastmcp.server.auth import RemoteAuthProvider  # noqa: E402
from fastmcp.server.auth.providers.jwt import JWTVerifier  # noqa: E402
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware  # noqa: E402
from fastmcp.server.transforms.search import BM25SearchTransform  # noqa: E402

from abstract.scopes import MCP_REQUIRED_SCOPES, scopes  # noqa: E402

from .middleware import DjangoRequestSignalsMiddleware  # noqa: E402
from .provider import AppMCPProvider  # noqa: E402

# Construct first: importing each app's `mcp` module registers the scopes advertised below.
mcp_provider = AppMCPProvider()

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
        "Use relay for email sending and receiving. Inspect the message log and "
        "message details. Read the documentation and how-tos for email "
        "deliverability, DNS, authentication, webhooks, and message statuses."
    ),
    auth=auth_provider,
    list_page_size=50,
    mask_error_details=not settings.DEBUG,
    strict_input_validation=True,
    providers=[mcp_provider],
)
mcp.add_middleware(DjangoRequestSignalsMiddleware())
mcp.add_middleware(StructuredLoggingMiddleware())
mcp.add_transform(BM25SearchTransform())


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


application = mcp.http_app(
    path="/mcp",
    # No shared session state across replicas and workers, so requests are independent.
    stateless_http=True,
    json_response=True,
    host_origin_protection=True,
    allowed_hosts=[*settings.ALLOWED_HOSTS, "localhost"],
    # Caddy terminates TLS, so trust the public origin rather than the ASGI scheme.
    allowed_origins=[settings.MCP_BASE_URL],
)
