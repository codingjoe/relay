import re
from base64 import b64encode
from hashlib import sha512

from django.conf import settings
from django.middleware.csp import (
    ContentSecurityPolicyMiddleware as DjangoContentSecurityPolicyMiddleware,
)
from django.urls import reverse

from .renderers import admin_rendering


class AdminFormRendererMiddleware:
    """Render admin form widgets with Django's stock templates."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = admin_rendering.set(request.path.startswith(reverse("admin:index")))
        try:
            return self.get_response(request)
        finally:
            admin_rendering.reset(token)


class ContentSecurityPolicyMiddleware(DjangoContentSecurityPolicyMiddleware):
    """
    Serve the enforced policy with the ESM import map hash added.

    A `304` carries no policy: the revalidating client keeps the one it cached
    with the body, import map hash included.
    """

    IMPORTMAP_PATTERN = re.compile(
        rb'<script[^>]*type="importmap"[^>]*>(?P<map>.*?)</script>', re.DOTALL
    )

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Integrity-Policy
    INTEGRITY_POLICY = "blocked-destinations=(script)"

    def hash_importmap_script(self, response) -> str | None:
        match = self.IMPORTMAP_PATTERN.search(getattr(response, "content", b""))
        if match is None:
            return None
        digest = sha512(match["map"]).digest()
        return f"'sha512-{b64encode(digest).decode()}'"

    def process_response(self, request, response):
        if response.status_code == 304:
            # A `304` has no body to hash, so the client keeps its cached policy.
            response._csp_config = None
            response._csp_ro_config = None
            return super().process_response(request, response)
        policy = settings.SECURE_CSP
        # A policy without script-src lets the browser fall back to
        # default-src. Appending to it would block every external script.
        script_src = policy.get("script-src") if policy else None
        if (
            script_src
            and not hasattr(response, "_csp_config")
            and (hash_source := self.hash_importmap_script(response))
        ):
            response._csp_config = policy | {"script-src": [*script_src, hash_source]}
        # https://bugs.webkit.org/show_bug.cgi?id=326341
        if not settings.DEBUG and self.IMPORTMAP_PATTERN.search(
            getattr(response, "content", b"")
        ):
            response.headers["Integrity-Policy-Report-Only"] = self.INTEGRITY_POLICY
        return super().process_response(request, response)
