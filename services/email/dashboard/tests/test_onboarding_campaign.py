import datetime

import pytest
from django.utils import timezone

from accounts.models import Membership
from domains.models import Domain
from services.email.dashboard import tasks
from services.email.dashboard.emails import (
    EMAIL_BY_STAGE,
    OnboardingFirstReminderEmail,
    OnboardingWelcomeEmail,
)
from services.email.dashboard.models import OnboardingMail
from services.email.dashboard.onboarding import OnboardingStep, get_onboarding_state
from services.email.msa.models import MsaCredential, OutgoingMessage


def use_locmem_mailer(settings):
    """Capture sent mail in `mailoutbox` instead of printing it."""
    settings.MAILERS = {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }


def complete_onboarding(org):
    """Send a message and connect an app, which is all the checklist asks for."""
    credential, raw_key = MsaCredential.objects.create_with_key(org=org)
    credential.verify_key(raw_key)
    OutgoingMessage.objects.create(
        org=org,
        rcpt_to="x@example.com",
        mail_from="y@example.com",
        domain=Domain.objects.get(org=org, is_managed=True),
    )


def test_email_by_stage_covers_every_stage():
    assert set(EMAIL_BY_STAGE) == set(OnboardingMail.Stage)


@pytest.mark.django_db
class TestGetOnboardingState:
    def test_state_names_the_first_unfinished_step(self, org):
        state = get_onboarding_state(org)

        assert state["next_step"] == OnboardingStep.TEST_MESSAGE
        assert state["onboarding_complete"] is False

    def test_state_moves_to_the_credential_after_a_message(self, org):
        OutgoingMessage.objects.create(
            org=org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
            domain=Domain.objects.get(org=org, is_managed=True),
        )

        assert get_onboarding_state(org)["next_step"] == OnboardingStep.CREDENTIAL


@pytest.mark.django_db
class TestSendOnboardingEmail:
    def test_send_onboarding_email__mails_admins_and_skips_write_members(
        self, org, other_user, mailoutbox, settings
    ):
        use_locmem_mailer(settings)
        Membership.objects.create(
            org=org,
            user=other_user,
            role=Membership.Role.WRITE,
        )

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingMail.Stage.WELCOME,
        )

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]

    def test_send_onboarding_email__records_the_mail(self, org, mailoutbox, settings):
        use_locmem_mailer(settings)

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingMail.Stage.WELCOME,
        )

        assert OnboardingMail.objects.filter(
            org=org, stage=OnboardingMail.Stage.WELCOME
        ).exists()

    def test_send_onboarding_email__does_not_repeat_a_mail(
        self, org, mailoutbox, settings
    ):
        use_locmem_mailer(settings)

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingMail.Stage.WELCOME,
        )
        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingMail.Stage.WELCOME,
        )

        assert len(mailoutbox) == 1

    def test_send_onboarding_email__leaves_a_finished_organization_alone(
        self, org, mailoutbox
    ):
        complete_onboarding(org)

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingMail.Stage.WELCOME,
        )

        assert not mailoutbox
        assert not OnboardingMail.objects.exists()


@pytest.mark.django_db
class TestSendDueOnboardingEmails:
    def test_send_due_onboarding_emails__sends_the_welcome_mail(
        self, org, mailoutbox, settings
    ):
        use_locmem_mailer(settings)

        tasks.send_due_onboarding_emails.func()

        assert len(mailoutbox) == 1
        assert OnboardingMail.objects.get(org=org).stage == OnboardingMail.Stage.WELCOME

    def test_send_due_onboarding_emails__does_not_repeat_a_mail(
        self, org, mailoutbox, settings
    ):
        use_locmem_mailer(settings)

        tasks.send_due_onboarding_emails.func()
        tasks.send_due_onboarding_emails.func()

        assert len(mailoutbox) == 1

    def test_send_due_onboarding_emails__skips_a_mail_that_is_not_due(
        self, org, mailoutbox, settings
    ):
        use_locmem_mailer(settings)
        OnboardingMail.objects.create(org=org, stage=OnboardingMail.Stage.WELCOME)

        tasks.send_due_onboarding_emails.func()

        assert not mailoutbox

    def test_send_due_onboarding_emails__skips_an_old_organization(
        self, org, mailoutbox
    ):
        org.created_at = timezone.now() - datetime.timedelta(days=30)
        org.save(update_fields=["created_at"])

        tasks.send_due_onboarding_emails.func()

        assert not mailoutbox

    def test_send_due_onboarding_emails__skips_a_suspended_organization(
        self, org, mailoutbox
    ):
        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at"])

        tasks.send_due_onboarding_emails.func()

        assert not mailoutbox


@pytest.mark.django_db
class TestOnboardingEmail:
    def test_subject__uses_the_stage_line(self, org, user):
        email = OnboardingFirstReminderEmail.to_user(
            user,
            org=org,
            state=get_onboarding_state(org),
            base_url="https://relay.example",
            language="en-us",
        )

        assert email.get_subject(**email.get_context_data()) == (
            "Press the button. Not the red one."
        )

    def test_context__names_the_next_step(self, org, user):
        email = OnboardingWelcomeEmail.to_user(
            user,
            org=org,
            state=get_onboarding_state(org),
            base_url="https://relay.example",
            language="en-us",
        )

        assert email.get_context_data()["next_step_button"] == "send test message"
        assert email.get_context_data()["onboarding_steps"][0]["done"] is False
