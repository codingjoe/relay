import json
import typing

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.humanize.templatetags.humanize import intcomma
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail
from django_letter.notifications import Notification

from accounts.models import Organization

from .onboarding import OnboardingStage, OnboardingStep

onboarding_notification = Notification(
    "onboarding",
    _("Onboarding tips"),
    _("A short series that walks you through your first send."),
)


class OnboardingEmail(TemplateEmail):
    """Walk an organization's admins through the first sending steps."""

    template_name = ""
    subject = ""
    preheader = ""
    mcp_question = ""

    def __init__(
        self,
        *,
        org: Organization,
        state: dict[str, typing.Any],
        **kwargs,
    ):
        self.org = org
        self.state = state
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
        """Fill in a sample organization and state when the caller passes none."""
        kwargs.setdefault("org", Organization(slug="acme"))
        kwargs.setdefault(
            "state",
            {
                "next_step": OnboardingStep.CREDENTIAL,
                "remaining_steps": len(OnboardingStep) - 1,
                "onboarding_steps": [
                    {
                        "label": step.label,
                        "done": step == OnboardingStep.TEST_MESSAGE,
                    }
                    for step in OnboardingStep
                ],
            },
        )
        extra_context = kwargs.setdefault("extra_context", {})
        extra_context.setdefault(
            "user",
            get_user_model()(
                username="jess",
                email="member@acme.example",
                first_name="Jess",
                last_name="Example",
            ),
        )
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        return super().get_context_data() | {
            "onboarding_steps": self.state["onboarding_steps"],
            "remaining_steps": self.state["remaining_steps"],
            "username": self.extra_context["user"].username,
            "short_name": self.extra_context["user"].get_short_name(),
            "free_monthly_messages": intcomma(settings.FREE_MONTHLY_MESSAGES),
            "mcp_codex_command": (
                f"codex mcp add relay --url {settings.MCP_RESOURCE_URL}"
            ),
            "mcp_claude_command": (
                f"claude mcp add --transport http relay {settings.MCP_RESOURCE_URL}"
            ),
            "mcp_config": json.dumps(
                {"mcpServers": {"relay": {"url": settings.MCP_RESOURCE_URL}}},
                separators=(",", ":"),
            ),
            "mcp_question": self.mcp_question,
            "next_step_button": self.state["next_step"].label,
            "next_step_url": reverse(
                "email-dashboard:get-started",
                kwargs={"org_slug": self.org.slug},
            ),
        }


@onboarding_notification
class OnboardingWelcomeEmail(OnboardingEmail):
    """Welcome a new organization with the free plan."""

    template_name = "emails/onboarding/welcome.html"
    subject = _("You send %(free_monthly_messages)s emails. Relay sends them free.")
    preheader = _("Send as much as you like, actually.")
    mcp_question = '"set up a project for relay"'


@onboarding_notification
class OnboardingFirstReminderEmail(OnboardingEmail):
    """Remind a new organization two days after its first admin joined."""

    template_name = "emails/onboarding/first_reminder.html"
    subject = _("Press the button. Not the red one.")
    preheader = _("There is a third button.")
    mcp_question = '"send a test email"'


@onboarding_notification
class OnboardingSecondReminderEmail(OnboardingEmail):
    """Remind a new organization six days after its first admin joined."""

    template_name = "emails/onboarding/second_reminder.html"
    subject = _("We keep your reputation out of the fire")
    preheader = _(
        "Spam checks, bounce lists, and the big providers telling relay when "
        "someone marks your message as spam."
    )
    mcp_question = '"list my messages"'


@onboarding_notification
class OnboardingLastReminderEmail(OnboardingEmail):
    """Send the last onboarding nudge thirteen days after its first admin joined."""

    template_name = "emails/onboarding/last_reminder.html"
    subject = _("You, AWS, and relay walk into an inbox")
    preheader = _("You already moved. AWS will cope.")
    mcp_question = "what landed in my inbox?"


EMAIL_BY_STAGE = {
    OnboardingStage.WELCOME: OnboardingWelcomeEmail,
    OnboardingStage.FIRST_REMINDER: OnboardingFirstReminderEmail,
    OnboardingStage.SECOND_REMINDER: OnboardingSecondReminderEmail,
    OnboardingStage.LAST_REMINDER: OnboardingLastReminderEmail,
}
