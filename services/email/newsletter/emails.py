import typing

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail
from django_letter.notifications import Notification

from captains_log.content import CaptainsLogContent

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
        request: HttpRequest | None = None,
        *,
        context: dict[str, typing.Any] | None = None,
        language: str | None = None,
        **kwargs,
    ) -> TemplateEmail:
        """Announce the newest log when the preview caller names none."""
        if "slug" not in kwargs:
            slug, metadata = next(iter(CaptainsLogContent.get_articles()))
            kwargs |= {"slug": slug, "metadata": metadata}
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        image = str(self.metadata.get("image", "")).removeprefix("images/")
        return super().get_context_data() | {
            "name": self.metadata["name"],
            "description": self.metadata.get("description", ""),
            "log_url": reverse("captains_log:detail", kwargs={"slug": self.slug}),
            "image_url": (
                reverse(
                    "captains_log:image",
                    kwargs={"slug": self.slug, "name": image},
                )
                if image
                else ""
            ),
        }
