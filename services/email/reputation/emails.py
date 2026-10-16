import typing

from django.contrib.humanize.templatetags.humanize import intcomma
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail

from .digest import sample_org_digest
from .evaluation import ReputationSummary


class WeeklyDigestEmail(TemplateEmail):
    """Report one organization's sending volume and its sender reputation."""

    template_name = "emails/weekly_digest.html"
    subject = _("%(organization)s sent %(sent)s messages out the door")
    subject_one = _("%(organization)s sent one message out the door")

    def __init__(self, *, digest: dict[str, typing.Any], **kwargs):
        self.digest = digest
        super().__init__(**kwargs)

    @classmethod
    def render_preview(
        cls,
        request: HttpRequest | None = None,
        *,
        context: dict[str, typing.Any] | None = None,
        language: str | None = None,
        **kwargs,
    ) -> TemplateEmail:
        """Fill in a busy window when the caller passes no digest."""
        kwargs.setdefault("digest", sample_org_digest())
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        return (
            super().get_context_data()
            | self.digest
            | {
                "headline": self.get_headline(
                    self.digest["stats"], self.digest["organization"]
                ),
                "sent": intcomma(self.digest["stats"]["total_sent"]),
                "verdict": self.get_verdict(self.digest["stats"]),
            }
        )

    def get_headline(self, stats: ReputationSummary, organization: str) -> str:
        """Return the words that open the mail, with no numbers in them."""
        match stats:
            case _ if stats["hard_bounce_over_limit"] or stats["complaint_over_limit"]:
                headline = _("Something to fix at %(organization)s.")
            case {"total_sent": 0}:
                headline = _("%(organization)s took the week off.")
            case {"hard_bounces": 0, "complaints": 0}:
                headline = _("A clean week at %(organization)s.")
            case _:
                headline = _("A week with a few bumps at %(organization)s.")
        return headline % {"organization": organization}

    def get_subject(self, **context) -> str:
        """Pick the subject that fits the count, then fill its placeholders."""
        match context["stats"]["total_sent"]:
            case 1:
                return self.subject_one % context
            case _:
                return super().get_subject(**context)

    def get_preheader(self, **context) -> str:
        return context["verdict"]

    def get_verdict(self, stats: ReputationSummary) -> str:
        """Return the one line that reads the numbers at a glance."""
        match stats:
            case {"hard_bounce_over_limit": True, "complaint_over_limit": True}:
                return _(
                    "The hard bounce rate and the complaint rate are both over "
                    "their limits. The numbers are below."
                )
            case {"hard_bounce_over_limit": True}:
                return _(
                    "The hard bounce rate is over its limit. The numbers are below."
                )
            case {"complaint_over_limit": True}:
                return _("The complaint rate is over its limit. The numbers are below.")
            case {"total_sent": 0}:
                return _(
                    "Nothing left the building. A spotless record, "
                    "achieved by doing nothing at all."
                )
            case {"hard_bounces": 0, "complaints": 0}:
                return _(
                    "Not one hard bounce. Receivers file your mail under inbox, "
                    "where the humans are."
                )
            case _:
                return _(
                    "A few bounces or complaints, comfortably inside the limits. "
                    "Boring is the goal, and this is boring."
                )
