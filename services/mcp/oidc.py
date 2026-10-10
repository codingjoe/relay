from typing import Any

from allauth.idp.oidc.adapter import DefaultOIDCAdapter
from allauth.idp.oidc.internal.oauthlib.server import get_server
from allauth.idp.oidc.internal.oauthlib.utils import (
    extract_params,
    respond_html_error,
)
from allauth.idp.oidc.views import AuthorizationView
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from oauthlib.oauth2.rfc6749.errors import FatalClientError, OAuth2Error
from oauthlib.openid.connect.core.exceptions import ConsentRequired

from abstract.scopes import scopes

# Imported for the registration side effect: the web process advertises the
# scopes every app declares in its own `mcp` module.
from services.mcp import components  # noqa: F401


class RelayOIDCAdapter(DefaultOIDCAdapter):
    """Advertise relay's registered scopes and issuer to MCP clients."""

    @property
    def scope_display(self) -> dict[str, str]:
        """Show relay's registered values on the consent screen."""
        return {**DefaultOIDCAdapter.scope_display, **scopes.display()}

    def populate_server_metadata(self, data: dict[str, str | list[str]]) -> None:
        """Advertise relay's scopes so clients request them on registration."""
        data["scopes_supported"] = list(self.scope_display)

    def get_issuer(self) -> str:
        """
        Return the issuer every MCP access token is minted with.

        `RELAY_MCP_OIDC_ISSUER_URL` keeps the single trailing slash that
        allauth strips, so the derived JWKS URL stays fetchable and the
        verifier matches the claim.
        """
        return settings.RELAY_MCP_OIDC_ISSUER_URL


class RelayAuthorizationView(AuthorizationView):
    """Serve allauth's consent screen, but never authorize silently."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """
        Handle the `prompt` parameter before allauth does.

        `prompt=none` is refused: allauth honors it for any scope granted to
        any token of the user, so a self-registered client could authorize
        itself with no UI. Anonymous `prompt=login` goes to relay's login page.
        """
        prompts = request.GET.get("prompt", "").split()
        if "none" in prompts:
            return self.refuse_silent_authorization(request)
        if "login" in prompts:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            # SOCIALACCOUNT_ONLY unmounts the re-authentication URL, so drop the prompt.
            request.GET = request.GET.copy()  # QueryDict is immutable.
            request.GET.pop("prompt", None)
        return super().get(request, *args, **kwargs)

    def refuse_silent_authorization(self, request: HttpRequest) -> HttpResponse:
        """
        Answer `prompt=none` with `consent_required` instead of a token.

        allauth grants silence for any scope granted to any of the user's
        tokens, whatever the client, and client registration is open, so a
        self-registered client could authorize against a logged-in account.
        """
        try:
            _, request_info = get_server().validate_authorization_request(
                *extract_params(request)
            )
        except (FatalClientError, ValidationError) as error:
            return respond_html_error(request, error=error)
        except OAuth2Error as error:
            return HttpResponseRedirect(error.in_uri(error.redirect_uri))
        error = ConsentRequired(state=request_info.get("state"))
        return HttpResponseRedirect(error.in_uri(request_info["redirect_uri"]))
