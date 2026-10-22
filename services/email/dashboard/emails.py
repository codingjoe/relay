import json
import typing

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_letter import TemplateEmail
from django_letter.notifications import Notification

from accounts.models import Organization

from .models import OnboardingCampaign
from .onboarding import OnboardingStep

NEXT_STEP_BUTTON = {
    OnboardingStep.TEST_MESSAGE: _("send test message"),
    OnboardingStep.CREDENTIAL: _("create sandbox key"),
    OnboardingStep.CONNECT: _("connect your app"),
}

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
        campaign: OnboardingCampaign,
        state: dict[str, typing.Any],
        **kwargs,
    ):
        self.campaign = campaign
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
        """Fill in a sample campaign and state when the caller passes none."""
        kwargs.setdefault(
            "campaign",
            OnboardingCampaign(org=Organization(slug="acme")),
        )
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
        return super().render_preview(
            request, context=context, language=language, **kwargs
        )

    def get_context_data(self) -> dict[str, typing.Any]:
        return super().get_context_data() | {
            "organization": self.campaign.org.slug,
            "onboarding_steps": self.state["onboarding_steps"],
            "remaining_steps": self.state["remaining_steps"],
            "free_monthly_messages": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "mcp_endpoint": settings.MCP_RESOURCE_URL,
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
            "next_step_button": NEXT_STEP_BUTTON[self.state["next_step"]],
            "next_step_url": reverse(
                "email-dashboard:get-started",
                kwargs={"org_slug": self.campaign.org.slug},
            ),
        }

    def get_subject(self, **context) -> str:
        """Fill the placeholders in the stage's subject."""
        return self.subject % context


@onboarding_notification
class OnboardingWelcomeEmail(OnboardingEmail):
    """Welcome a new organization with the free plan."""

    template_name = "emails/onboarding/welcome.html"
    subject = _("One does not simply send %(limit)s emails for free")
    preheader = _("Turns out you can.")
    mcp_question = '"show my domains"'

    def get_subject(self, **context) -> str:
        """Fill the placeholders, including the free monthly volume."""
        return super().get_subject(
            **(context | {"limit": intcomma(settings.RELAY_FREE_MONTHLY_MESSAGES)})
        )


@onboarding_notification
class OnboardingFirstReminderEmail(OnboardingEmail):
    """Remind a new organization one day after its first admin joined."""

    template_name = "emails/onboarding/first_reminder.html"
    subject = _("Press the button. Not the red one.")
    preheader = _("There is a third button.")
    mcp_question = '"send a test email"'


@onboarding_notification
class OnboardingSecondReminderEmail(OnboardingEmail):
    """Remind a new organization three days after its first admin joined."""

    template_name = "emails/onboarding/second_reminder.html"
    subject = _("We keep your reputation out of the fire")
    preheader = _("Spam checks, bounce lists, and provider feedback.")
    mcp_question = '"list my messages"'


@onboarding_notification
class OnboardingLastReminderEmail(OnboardingEmail):
    """Send the last onboarding nudge one week after its first admin joined."""

    template_name = "emails/onboarding/last_reminder.html"
    subject = _("You, AWS, and relay walk into an inbox")
    preheader = _("You already moved. AWS will cope.")
    mcp_question = "what landed in my inbox?"


EMAIL_BY_STAGE = {
    OnboardingCampaign.Stage.WELCOME: OnboardingWelcomeEmail,
    OnboardingCampaign.Stage.FIRST_REMINDER: OnboardingFirstReminderEmail,
    OnboardingCampaign.Stage.SECOND_REMINDER: OnboardingSecondReminderEmail,
    OnboardingCampaign.Stage.LAST_REMINDER: OnboardingLastReminderEmail,
}
