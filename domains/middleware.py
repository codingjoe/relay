from django.conf import settings
from django.http import Http404, HttpResponse
from django.http.request import validate_host

from .views import MtaStsAuthorizeView, MtaStsPolicyView


class MtaStsHostMiddleware:
    """Serve the MTA-STS policy and approve on-demand TLS before Django validates ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.META.get("PATH_INFO", "")
        host = request.META.get("HTTP_HOST", "").split(":")[0].lower()
        match path, host.startswith("mta-sts."):
            # Caddy is the only ingress. It serves the public site addresses in
            # ALLOWED_HOSTS and answers other hosts with the 421 catch-all.
            # Caddy calls this path as http://web:8000, so a request with a host
            # outside ALLOWED_HOSTS comes from the internal network.
            case ("/internal/mta-sts/authorize/", _) if not validate_host(
                host, settings.ALLOWED_HOSTS
            ):
                response = MtaStsAuthorizeView.as_view()(request)
            case ("/.well-known/mta-sts.txt", True):
                try:
                    response = MtaStsPolicyView.as_view()(request)
                    if hasattr(response, "render") and callable(response.render):
                        response.render()
                except Http404:
                    response = HttpResponse(status=421)
            case _:
                response = self.get_response(request)
        return response
