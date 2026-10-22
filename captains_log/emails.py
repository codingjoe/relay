import typing

from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail
from django_letter.notifications import Notification

from .content import CaptainsLogContent

station_log_notification = Notification(
    "station-log",
    _("Station log"),
    _("A note when a new product update is published."),
)


@station_log_notification
class StationLogEmail(TemplateEmail):
    """Announce one published station log."""

    template_name = "emails/station_log.html"
    subject = _("A new station log: %(name)s")
    preheader = "%(description)s"

    def __init__(
        self,
        *,
        slug: str,
        metadata: dict[str, typing.Any],
        **kwargs,
    ) -> None:
        self.slug = slug
        self.metadata = metadata
        super().__init__(**kwargs)

    @classmethod
    def render_preview(
        cls,
        request=None,
        *,
        context=None,
        language=None,
        **kwargs,
    ):
        """Announce the newest log when the preview caller names none."""
        if "slug" not in kwargs:
            try:
                slug, metadata = next(iter(CaptainsLogContent.get_articles()))
            except StopIteration:
                raise Http404 from None
            kwargs |= {"slug": slug, "metadata": metadata}
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self):
        return super().get_context_data() | {
            "name": self.metadata["name"],
            "description": self.metadata.get("description", ""),
            "log_url": reverse("captains_log:detail", kwargs={"slug": self.slug}),
            "content_html": CaptainsLogContent.render_body(self.slug),
        }
