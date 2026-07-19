"""Legal page views — imprint, terms, privacy."""

from django.utils.translation import gettext_lazy as _

from abstract.views import MarkdownView


class ImprintView(MarkdownView):
    title = _("imprint")
    markdown_template = "imprint.md"


class TermsView(MarkdownView):
    title = _("terms of service")
    markdown_template = "terms.md"


class PrivacyView(MarkdownView):
    title = _("privacy policy")
    markdown_template = "privacy.md"
