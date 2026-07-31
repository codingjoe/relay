from django.http import Http404, HttpResponse

from .views import MtaStsPolicyView


class MtaStsHostMiddleware:
    """Serve the MTA-STS policy for mta-sts.* hosts before Django validates ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get("HTTP_HOST", "").split(":")[0].lower()
        path = request.META.get("PATH_INFO", "")
        if host.startswith("mta-sts.") and path == "/.well-known/mta-sts.txt":
            try:
                response = MtaStsPolicyView.as_view()(request)
                if hasattr(response, "render") and callable(response.render):
                    response.render()
                return response
            except Http404:
                return HttpResponse(status=421)
        return self.get_response(request)
