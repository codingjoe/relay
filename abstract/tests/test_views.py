import datetime

import pytest
from django.http import Http404
from django.test import RequestFactory

from abstract.views import CacheControlMixin, MarkdownArticleMixin, MarkdownView


class TestCacheControlMixin:
    def test_get_cache_directives__converts_durations_to_seconds(self):
        class TestView(CacheControlMixin):
            cache_control = {"public": True, "max_age": datetime.timedelta(minutes=5)}

        assert TestView().get_cache_directives() == {"public": True, "max_age": 300}

    def test_get_cache_directives__keeps_plain_seconds(self):
        class TestView(CacheControlMixin):
            cache_control = {"private": True, "max_age": 60}

        assert TestView().get_cache_directives() == {"private": True, "max_age": 60}


class TestMarkdownArticleMixin:
    def test_get_article_path__returns_existing_file(self, tmp_path):
        (tmp_path / "exists.md").write_text("Body.")

        class TestArticleView(MarkdownArticleMixin):
            docs_dir = tmp_path
            slugs = frozenset({"exists"})

        assert TestArticleView.get_article_path("exists") == tmp_path / "exists.md"

    def test_get_article_path__stale_slug_raises_404(self, tmp_path):
        """
        A slug in the allowlist whose file is gone must 404, not 500.

        The slugs frozenset is a module-level cache. A server that
        outlives a file rename must degrade to 404.
        """

        class TestArticleView(MarkdownArticleMixin):
            docs_dir = tmp_path
            slugs = frozenset({"renamed"})

        with pytest.raises(Http404):
            TestArticleView.get_article_path("renamed")

    def test_get_article_path__unknown_slug_raises_404(self, tmp_path):
        class TestArticleView(MarkdownArticleMixin):
            docs_dir = tmp_path
            slugs = frozenset()

        with pytest.raises(Http404):
            TestArticleView.get_article_path("unknown")

    def test_get_articles__skips_stale_slugs(self, tmp_path):
        (tmp_path / "exists.md").write_text("---\nname: Exists\n---\nBody.")

        class TestArticleView(MarkdownArticleMixin):
            docs_dir = tmp_path
            slugs = frozenset({"exists", "renamed"})

        articles = dict(TestArticleView.get_articles())
        assert list(articles) == ["exists"]
        assert articles["exists"]["name"] == "Exists"


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
