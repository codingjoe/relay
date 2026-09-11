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
            # Caddy serves the public site addresses from ALLOWED_HOSTS, so a
            # request for any other host can only come from inside the network.
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
