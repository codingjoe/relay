import itertools

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.template import engines as template_engines
from django.test import RequestFactory
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
