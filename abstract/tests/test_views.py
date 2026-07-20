from django.test import RequestFactory

from abstract.views import MarkdownView


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
        view = MarkdownView()
        view.title = "Test"
        view.breadcrumbs = [("Home", "home")]
        view.request = RequestFactory().get("/test/")
        breadcrumbs = view.get_context_data()["breadcrumb_trail"]
        assert breadcrumbs[-1]["label"] == "Test"
        assert breadcrumbs[-1]["url"] is None
        assert breadcrumbs[0]["label"] == "Home"
