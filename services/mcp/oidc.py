import typing
from urllib.parse import urlsplit

from allauth.idp.oidc.adapter import DefaultOIDCAdapter
from allauth.idp.oidc.internal.oauthlib.server import get_server
from allauth.idp.oidc.internal.oauthlib.utils import (
    extract_params,
    respond_html_error,
)
from allauth.idp.oidc.models import Client, Token
from allauth.idp.oidc.views import AuthorizationView as BaseAuthorizationView
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from oauthlib.oauth2.rfc6749.errors import FatalClientError, OAuth2Error
from oauthlib.openid.connect.core.exceptions import ConsentRequired

from abstract.scopes import scopes

# Imported for its registration side effect: every app advertises scopes in its own `mcp` module.
from services.mcp import components  # noqa: F401

from .forms import ConsentAuthorizationForm


class OIDCAdapter(DefaultOIDCAdapter):
    """Advertise registered scopes and issuer to MCP clients."""

    @property
    def scope_display(self) -> dict[str, str]:
        return {**DefaultOIDCAdapter.scope_display, **scopes.display()}

    def populate_server_metadata(self, data: dict[str, str | list[str]]) -> None:
        data["scopes_supported"] = list(self.scope_display)

    def validate_client_registration(
        self,
        *,
        client: Client,
        client_metadata: dict[str, typing.Any],
        token: Token | None,
        bearer_token: str | None,
        **kwargs: typing.Any,
    ) -> None:
        super().validate_client_registration(
            client=client,
            client_metadata=client_metadata,
            token=token,
            bearer_token=bearer_token,
            **kwargs,
        )
        # Registration defaults to openid, yet the challenge needs more, so clients that omit scopes could never honour it.
        client.set_scopes(sorted({*client.get_scopes(), *scopes.supported()}))

    def get_issuer(self) -> str:
        return settings.MCP_OIDC_ISSUER_URL


class AuthorizationView(BaseAuthorizationView):
    """Serve the consent screen, but never authorize silently."""

    template_name = "mcp/authorization_form.html"
    form_class = ConsentAuthorizationForm

    def get_form_kwargs(self) -> dict[str, typing.Any]:
        kwargs = super().get_form_kwargs()
        if not kwargs["requested_scopes"]:
            # Clients that request no scope still get an actionable consent screen limited to registered scopes.
            client = Client.objects.get(pk=self._request_info["client_id"])
            kwargs["requested_scopes"] = client.get_scopes()
        return kwargs

    def get_context_data(self, **kwargs: typing.Any) -> dict[str, typing.Any]:
        return super().get_context_data(**kwargs) | {
            "redirect_hostname": urlsplit(self._request_info["redirect_uri"]).hostname
        }

    def get(
        self, request: HttpRequest, *args: typing.Any, **kwargs: typing.Any
    ) -> HttpResponse:
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
