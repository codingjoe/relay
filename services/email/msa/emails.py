import typing

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail

from accounts.models import Organization
from domains.models import Domain


class TestEmail(TemplateEmail):
    """Send one templated test message to an organization member."""

    template_name = "emails/test_email.html"
    subject = _("Test email from %(domain)s")

    def __init__(self, *, domain, **kwargs):
        self.domain = domain
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
        extra_context = kwargs.setdefault("extra_context", {})
        extra_context.setdefault("user", get_user_model()(email="member@acme.example"))
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        context = super().get_context_data()
        message_list_url = reverse(
            "message:message-list", kwargs={"org_slug": self.domain.org.slug}
        )
        return context | {
            "domain": self.domain.name,
            "sender": f"{settings.RELAY_POSTMASTER_LOCAL_PART}@{self.domain.name}",
            "recipient": context["user"].email,
            "dashboard_url": f"{self.get_base_url().rstrip('/')}{message_list_url}",
        }
