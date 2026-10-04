import base64
import hashlib
import itertools
import json
import re

from django.http import HttpResponse, StreamingHttpResponse
from django.urls import reverse
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override

from root.middleware import ContentSecurityPolicyMiddleware

IMPORTMAP_TAG = '<script type="importmap">{"imports": {}}</script>'
SCRIPT_TAG = re.compile(rb"<script\b[^>]*>")


class TestContentSecurityPolicyMiddleware:
    def test_process_response__adds_the_import_map_hash(self, rf):
        response = HttpResponse(
            '<html><script type="importmap">{"imports": {}}</script></html>'
        )
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        digest = base64.b64encode(hashlib.sha512(b'{"imports": {}}').digest()).decode()
        assert f"'sha512-{digest}'" in response.headers["Content-Security-Policy"]

    def test_process_response__hashes_the_map_the_page_carries(self, client):
        response = client.get(reverse("home"))
        content = response.content.decode()
        open_tag = '<script type="importmap">'
        start = content.index(open_tag) + len(open_tag)
        rendered_map = content[start : content.index("</script>", start)]
        digest = base64.b64encode(
            hashlib.sha512(rendered_map.encode()).digest()
        ).decode()
        assert f"'sha512-{digest}'" in response.headers["Content-Security-Policy"]

    def test_process_response__serves_no_hash_without_the_map(self, rf):
        response = HttpResponse('{"ok": true}', content_type="application/json")
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        assert "'sha512-" not in response.headers["Content-Security-Policy"]

    def test_process_response__skips_a_policy_without_script_src(self, settings, rf):
        settings.SECURE_CSP = {"default-src": [CSP.SELF]}
        response = HttpResponse('<script type="importmap">{"imports": {}}</script>')
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        assert response.headers["Content-Security-Policy"] == "default-src 'self'"

    def test_process_response__keeps_the_policy_of_the_view(self, rf):
        @csp_override({"default-src": [CSP.NONE]})
        def view(request):
            return HttpResponse()

        response = view(rf.get("/"))
        middleware = ContentSecurityPolicyMiddleware(view)
        request = rf.get("/")
        response = middleware.process_response(request, response)
        assert response.headers["Content-Security-Policy"] == "default-src 'none'"

    def test_process_response__every_script_a_page_loads_carries_integrity(
        self, client
    ):
        urls = [reverse("home"), reverse("docs:detail", kwargs={"slug": "security"})]
        for url in urls:
            response = client.get(url)
            content = response.content.decode()
            start = content.index('<script type="importmap">') + len(
                '<script type="importmap">'
            )
            importmap = json.loads(content[start : content.index("</script>", start)])
            loaded = [
                tag for tag in SCRIPT_TAG.findall(response.content) if b"src=" in tag
            ]
            assert loaded
            for tag in loaded:
                source = re.search(rb'src="(?P<url>[^"]*)"', tag)["url"].decode()
                assert b"integrity=" in tag, f"{url} loads {source} without a hash"
                assert source in importmap["integrity"]

    def test_process_response__enforces_the_integrity_policy(self, client):
        response = client.get(reverse("home"))
        assert response.headers["Integrity-Policy"] == "blocked-destinations=(script)"

    def test_process_response__skips_the_integrity_policy_in_debug(self, settings, rf):
        settings.DEBUG = True
        response = HttpResponse(IMPORTMAP_TAG)
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        assert "Integrity-Policy" not in response.headers

    def test_process_response__serves_no_integrity_policy_without_the_map(self, rf):
        response = HttpResponse('{"ok": true}', content_type="application/json")
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        assert "Integrity-Policy" not in response.headers

    def test_process_response__keeps_a_streaming_response_streaming(self, rf):
        response = StreamingHttpResponse(itertools.repeat(b"<script></script>"))
        middleware = ContentSecurityPolicyMiddleware(lambda request: response)
        response = middleware.process_response(rf.get("/"), response)
        assert response.streaming
