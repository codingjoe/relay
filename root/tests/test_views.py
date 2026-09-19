import itertools

import pytest
from django.conf import settings
from django.db import connections
from django.http import HttpResponse
from django.template import engines as template_engines
from django.test import RequestFactory
from django.urls import reverse
from django.utils.module_loading import import_string

from root.views import HomeView


class TestHomeView:
    def test_get_context_data__nameservers_from_host(self, settings):
        settings.ALLOWED_HOSTS = ["my.platform.com", "localhost", "localhost:8000"]
        view = HomeView()
        view.request = RequestFactory().get("/", HTTP_HOST="my.platform.com")
        context = view.get_context_data()
        assert context["nameservers"] == ["ns1.my.platform.com", "ns2.my.platform.com"]

    def test_get_context_data__strips_port_from_host(self, settings):
        settings.ALLOWED_HOSTS = ["localhost", "localhost:8000"]
        view = HomeView()
        view.request = RequestFactory().get("/", HTTP_HOST="localhost:8000")
        context = view.get_context_data()
        assert context["nameservers"] == ["ns1.localhost", "ns2.localhost"]


class TestHomeViewRender:
    def test_get__renders_for_anonymous(self, client):
        response = client.get("/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_get__renders_for_authenticated(self, admin_client):
        response = admin_client.get("/")
        assert response.status_code == 200


class TestHomeViewPricing:
    def test_get__shows_the_configured_free_tier(self, client, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = 2000

        text = " ".join(client.get("/").content.decode().split())

        assert "First 2,000 emails free every month" in text
        assert 'min="2000"' in text
        assert 'value="2000"' in text
        assert '<span id="price-volume">2,000</span>' in text

    def test_get__shows_a_changed_price(self, client, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 2.5

        text = " ".join(client.get("/").content.decode().split())

        assert "First 1,000 emails free, then €2.50 / 1,000 emails." in text
        assert 'data-per-thousand="2.5"' in text

    def test_get__without_a_price__shows_only_the_free_tier(self, client, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 0.0

        text = " ".join(client.get("/").content.decode().split())

        assert "First 1,000 emails free, every month." in text
        assert "then €" not in text
        assert "/ 1,000 emails." not in text

    def test_get__with_a_negative_price__shows_only_the_free_tier(
        self, client, settings
    ):
        settings.RELAY_PRICE_PER_1000_MESSAGES = -5.0

        text = " ".join(client.get("/").content.decode().split())

        assert "First 1,000 emails free, every month." in text
        assert 'data-per-thousand="0"' in text
        assert "€-" not in text


class TestPublicChrome:
    """Public pages render the static chrome: no session access, no Vary: Cookie."""

    public_urls = [
        "/",
        "/docs/security/",
        "/legal/imprint/",
    ]

    def test_get__no_vary_cookie(self, client):
        for url in self.public_urls:
            response = client.get(url)
            assert response.status_code == 200
            assert "Cookie" not in (response.headers.get("Vary") or "")

    @pytest.mark.django_db
    def test_get__no_vary_cookie_when_authenticated(self, admin_client):
        for url in self.public_urls:
            response = admin_client.get(url)
            assert response.status_code == 200
            assert "Cookie" not in (response.headers.get("Vary") or "")

    @staticmethod
    def track_queries(request):
        """Return the SQL statements executed while calling `request()`."""
        queries = []

        def tracker(execute, sql, params, many, context):
            queries.append(sql)
            return execute(sql, params, many, context)

        wrappers = [alias.execute_wrapper(tracker) for alias in connections.all()]
        for wrapper in wrappers:
            wrapper.__enter__()
        request()
        for wrapper in wrappers:
            wrapper.__exit__(None, None, None)
        return queries

    def test_get__no_queries(self, client):
        for url in self.public_urls:
            queries = self.track_queries(lambda url=url: client.get(url))
            assert not queries, f"{url} ran {len(queries)} queries"

    @pytest.mark.django_db
    def test_get__no_queries_when_authenticated(self, admin_client):
        for url in self.public_urls:
            queries = self.track_queries(lambda url=url: admin_client.get(url))
            assert not queries, f"{url} ran {len(queries)} queries"

    def test_get__renders_static_chrome(self, client):
        for url in self.public_urls:
            body = client.get(url).content.decode()
            assert 'id="toaster"' not in body
            assert "gravatar.com" not in body
        response = client.get("/docs/security/")
        body = response.content.decode()
        assert reverse("accounts:org-start") in body

    @pytest.mark.django_db
    def test_get__renders_static_chrome_when_authenticated(self, admin_client):
        for url in self.public_urls:
            body = admin_client.get(url).content.decode()
            assert 'id="toaster"' not in body
            assert "gravatar.com" not in body
        response = admin_client.get("/docs/security/")
        body = response.content.decode()
        assert reverse("accounts:org-start") in body


class TestNoIO:
    """Guard against eager database access in middleware and context processors."""

    def build_middleware_chain(self, get_response):
        """Wrap `get_response` with every configured middleware in settings order."""
        handler = get_response
        for middleware_path in reversed(settings.MIDDLEWARE):
            middleware_cls = import_string(middleware_path)
            handler = middleware_cls(handler)
        return handler

    def test_middleware_does_not_touch_db(self, rf, django_db_blocker):
        request = rf.get("/")

        def get_response(req):
            return HttpResponse(b"", status=200)

        handler = self.build_middleware_chain(get_response)
        with django_db_blocker.block():
            try:
                handler(request)
            except RuntimeError:
                pytest.fail("Middleware performed I/O during request processing")

    @pytest.mark.parametrize(
        "fn",
        list(
            itertools.chain(
                *(
                    backend.engine.template_context_processors
                    for backend in template_engines.all()
                )
            )
        ),
    )
    def test_context_processors_do_not_touch_db(self, fn, rf, django_db_blocker):
        request = rf.get("/")

        def get_response(req):
            return HttpResponse(b"", status=200)

        handler = self.build_middleware_chain(get_response)
        handler(request)

        with django_db_blocker.block():
            try:
                fn(request)
            except RuntimeError:
                pytest.fail(
                    f"Context processor {fn.__module__}.{fn.__name__} performed I/O"
                )
            except AttributeError as e:
                pytest.fail(
                    f"Context processor {fn.__module__}.{fn.__name__} "
                    f"eagerly accessed request attribute: {e}"
                )
