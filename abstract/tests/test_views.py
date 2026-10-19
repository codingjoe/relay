import datetime
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory
from django.views import generic

from abstract.views import (
    CacheControlMixin,
    ConditionalGetMixin,
    MarkdownView,
    get_release_etag,
)


class TestGetReleaseEtag:
    def test_get_release_etag__namespaces_the_validator(self, settings):
        settings.SENTRY_RELEASE = "sha-abc"

        assert get_release_etag("1a-2b") == '"sha-abc:1a-2b"'

    def test_get_release_etag__strips_the_quotes_and_the_weak_prefix(self, settings):
        settings.SENTRY_RELEASE = "sha-abc"

        assert get_release_etag('W/"1a-2b"') == '"sha-abc:1a-2b"'

    def test_get_release_etag__keeps_the_validator_without_a_release(self, settings):
        settings.SENTRY_RELEASE = ""

        assert get_release_etag('"1a-2b"') == '"1a-2b"'

    def test_get_release_etag__serves_no_etag_for_none(self, settings):
        settings.SENTRY_RELEASE = "sha-abc"

        assert get_release_etag(None) is None


class TestConditionalGetMixin:
    def test_get__scopes_an_overridden_etag(self, settings, rf):
        """A view that overrides get_etag still carries the release."""

        class TestView(ConditionalGetMixin, generic.View):
            object = SimpleNamespace(
                pk=1, modified_at=datetime.datetime.now(datetime.UTC)
            )

            def get_object(self):
                return self.object

            def get_etag(self, obj):
                return '"override"'

            def get_context_data(self, **kwargs):
                return {}

            def render_to_response(self, context):
                return HttpResponse("ok")

        settings.SENTRY_RELEASE = "sha-abc"

        response = TestView.as_view()(rf.get("/"))

        assert response.headers["ETag"] == '"sha-abc:override"'


class TestCacheControlMixin:
    def test_get_cache_directives__converts_durations_to_seconds(self):
        class TestView(CacheControlMixin):
            cache_control = {"public": True, "max_age": datetime.timedelta(minutes=5)}

        assert TestView().get_cache_directives() == {"public": True, "max_age": 300}

    def test_get_cache_directives__keeps_plain_seconds(self):
        class TestView(CacheControlMixin):
            cache_control = {"private": True, "max_age": 60}

        assert TestView().get_cache_directives() == {"private": True, "max_age": 60}


class TestMarkdownView:
    def test_get_context_data__has_title(self):
        view = MarkdownView()
        view.title = "Test Page"
        view.request = RequestFactory().get("/test/")
        assert view.get_context_data()["title"] == "Test Page"

    def test_get_context_data__has_markdown_template(self):
        view = MarkdownView()
        view.title = "T"
        view.markdown_template = "doc.md"
        view.request = RequestFactory().get("/test/")
        assert view.get_context_data()["markdown_template"] == "doc.md"

    def test_get_context_data__has_toc_levels(self):
        view = MarkdownView()
        view.title = "T"
        view.request = RequestFactory().get("/test/")
        assert view.get_context_data()["toc_levels"] == "2-3"

    def test_get_context_data__has_breadcrumbs(self):
        class TestMarkdownView(MarkdownView):
            title = "Test"
            parent = "home"

        view = TestMarkdownView()
        view.request = RequestFactory().get("/test/")
        breadcrumbs = view.get_context_data()["breadcrumbs"]
        assert breadcrumbs[-1]["title"] == "Test"
        assert breadcrumbs[-1]["url"] is None
        assert breadcrumbs[0]["title"] == "Home"
