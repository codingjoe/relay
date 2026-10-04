import re
from base64 import b64encode
from hashlib import sha512

from django.conf import settings
from django.middleware.csp import (
    ContentSecurityPolicyMiddleware as DjangoContentSecurityPolicyMiddleware,
)
from django.utils.csp import CSP


class ContentSecurityPolicyMiddleware(DjangoContentSecurityPolicyMiddleware):
    """Serve the enforced policy with the ESM import map hashed and SRI required."""

    ADMIN_NAMESPACE = "admin"

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
        policy = settings.SECURE_CSP
        # A policy without script-src lets the browser fall back to
        # default-src. Appending to it would block every external script.
        script_src = policy.get("script-src") if policy else None
        resolver_match = request.resolver_match
        is_admin = bool(
            resolver_match and resolver_match.namespace == self.ADMIN_NAMESPACE
        )
        if script_src and not hasattr(response, "_csp_config"):
            # Unfold's Alpine runtime compiles expressions with the Function
            # constructor, which a strict script-src blocks. Only the staff-only
            # admin runs it.
            # https://github.com/unfoldadmin/django-unfold/issues/1535
            if is_admin and CSP.UNSAFE_EVAL not in script_src:
                script_src = [*script_src, CSP.UNSAFE_EVAL]
                response._csp_config = policy | {"script-src": script_src}
            if hash_source := self.hash_importmap_script(response):
                response._csp_config = policy | {
                    "script-src": [*script_src, hash_source]
                }
        # The debug toolbar injects module scripts the import map does not pin.
        if not settings.DEBUG and self.IMPORTMAP_PATTERN.search(
            getattr(response, "content", b"")
        ):
            response.headers["Integrity-Policy"] = self.INTEGRITY_POLICY
        return super().process_response(request, response)
