import typing
import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail

from abstract.email_utils import decode_header_value
from accounts.models import Organization

from .models import IncomingMessage


class PostmasterForwardEmail(TemplateEmail):
    """Forward one inbound postmaster message to an organization member."""

    template_name = "emails/postmaster_forward.html"
    subject = _("Fwd: %(original_subject)s")

    def __init__(self, message, *, language=None, base_url=None, **kwargs):
        self.sender = (
            decode_header_value(message.parsed_email().get("From", ""))
            or message.mail_from
        )
        self.incoming_message = message
        super().__init__(
            language=language or settings.LANGUAGE_CODE,
            base_url=base_url or settings.RELAY_PLATFORM_BASE_URL,
            reply_to=[self.sender] if self.sender else None,
            **kwargs,
        )

    @classmethod
    def render_preview(
        cls,
        request: HttpRequest | None = None,
        *,
        context: dict[str, typing.Any] | None = None,
        language: str | None = None,
        **kwargs,
    ) -> TemplateEmail:
        """Fall back to a sample message when the preview caller passes none."""
        if "message" not in kwargs:
            kwargs["message"] = IncomingMessage(
                org=Organization(slug="acme"),
                pk=uuid.uuid7(),
                content_type=ContentType.objects.get_for_model(IncomingMessage),
                mail_from="sender@example.org",
                rcpt_to=f"postmaster@{settings.RELAY_PLATFORM_DOMAIN}",
                subject="Delivery delayed",
            )
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, str]:
        return {
            "original_subject": self.incoming_message.subject,
            "sender": self.sender,
            "recipient": self.incoming_message.rcpt_to,
            "detail_url": f"{self.base_url}{self.incoming_message.get_absolute_url()}",
        }
