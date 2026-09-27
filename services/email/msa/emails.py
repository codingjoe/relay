import typing
import uuid

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail

from accounts.models import Organization
from domains.models import Domain

from .submission import get_submission_context


class TestEmail(TemplateEmail):
    """Send one templated test message to an organization member."""

    template_name = "emails/test_email.html"
    subject = _("Test email from %(domain)s")
    preheader = _("How to send the next message from your own application.")

    def __init__(self, *, domain, message_pk, **kwargs):
        self.domain = domain
        self.message_pk = message_pk
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
        """Fill in sample values for any argument the preview caller omits."""
        kwargs.setdefault(
            "domain", Domain(name="acme.example", org=Organization(slug="acme"))
        )
        kwargs.setdefault("message_pk", uuid.uuid7())
        extra_context = kwargs.setdefault("extra_context", {})
        extra_context.setdefault("user", get_user_model()(email="member@acme.example"))
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        context = super().get_context_data()
        return (
            context
            | get_submission_context()
            | {
                "domain": self.domain.name,
                "username": self.domain.org.slug,
                "message_pk": self.message_pk,
            }
        )
