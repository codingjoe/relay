from abstract.views import MarkdownView
from legal.views import ImprintView, PrivacyView, TermsView


class TestLegalViews:
    def test_imprint_view__attributes(self):
        assert str(ImprintView.title) == "imprint"
        assert ImprintView.markdown_template == "imprint.md"

    def test_terms_view__attributes(self):
        assert str(TermsView.title) == "terms of service"
        assert TermsView.markdown_template == "terms.md"

    def test_privacy_view__attributes(self):
        assert str(PrivacyView.title) == "privacy policy"
        assert PrivacyView.markdown_template == "privacy.md"

    def test_legal_views__inherit_markdown_view(self):
        assert issubclass(ImprintView, MarkdownView)
        assert issubclass(TermsView, MarkdownView)
        assert issubclass(PrivacyView, MarkdownView)
