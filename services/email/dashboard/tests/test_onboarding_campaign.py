import datetime

import pytest
from django.core.mail.backends import locmem
from django.utils import timezone

from accounts.models import Membership, Organization
from domains.models import Domain
from services.email.dashboard import tasks
from services.email.dashboard.emails import EMAIL_BY_STAGE, OnboardingWelcomeEmail
from services.email.dashboard.onboarding import (
    SEND_OFFSETS,
    OnboardingStage,
    OnboardingStep,
    get_onboarding_state,
    send_time,
)
from services.email.msa.models import MsaCredential, OutgoingMessage

REFUSED_ADDRESS = "bob@example.com"  # the other_user fixture's address


class RefusedConnectionError(OSError):
    """A refused connection, the way a dead SMTP host raises it."""


class RefusedEmailBackend(locmem.EmailBackend):
    """Refuse every message the way a dead SMTP host would."""

    def send_messages(self, email_messages):
        raise RefusedConnectionError


class RefusedAddressEmailBackend(locmem.EmailBackend):
    """Refuse one address the way a dead SMTP host would."""

    def send_messages(self, email_messages):
        for message in email_messages:
            if REFUSED_ADDRESS in message.to:
                raise RefusedConnectionError
        return super().send_messages(email_messages)


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
    assert set(EMAIL_BY_STAGE) == set(OnboardingStage)


def test_send_offsets__cover_every_stage():
    assert set(SEND_OFFSETS) == set(OnboardingStage)


def test_send_time__returns_the_start_for_a_zero_offset():
    start = timezone.now().replace(year=2026, month=10, day=23, hour=14, minute=30)

    assert send_time(start, datetime.timedelta(0)) == start


def test_send_time__waits_for_the_next_weekday_morning():
    friday = timezone.now().replace(
        year=2026, month=10, day=23, hour=14, minute=30, second=0, microsecond=0
    )

    assert send_time(friday, datetime.timedelta(days=1)) == friday.replace(
        day=26, hour=9, minute=0
    )


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
        self, org, other_user, mailoutbox
    ):
        Membership.objects.create(
            org=org,
            user=other_user,
            role=Membership.Role.WRITE,
        )

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingStage.WELCOME,
        )

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]

    def test_send_onboarding_email__leaves_a_finished_organization_alone(
        self, org, mailoutbox
    ):
        complete_onboarding(org)

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingStage.WELCOME,
        )

        assert not mailoutbox

    def test_send_onboarding_email__leaves_a_suspended_organization_alone(
        self, org, mailoutbox
    ):
        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at"])

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingStage.WELCOME,
        )

        assert not mailoutbox

    def test_send_onboarding_email__keeps_going_when_one_admin_fails(
        self, org, other_user, mailoutbox, settings
    ):
        Membership.objects.create(
            org=org,
            user=other_user,
            role=Membership.Role.ADMIN,
        )
        settings.MAILERS = {
            "default": {"BACKEND": f"{__name__}.RefusedAddressEmailBackend"}
        }

        tasks.send_onboarding_email.func(
            org_pk=org.pk,
            stage=OnboardingStage.WELCOME,
        )

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]

    def test_send_onboarding_email__drops_a_missing_organization(self, org, mailoutbox):
        tasks.send_onboarding_email.func(
            org_pk=org.pk + 1,
            stage=OnboardingStage.WELCOME,
        )

        assert not mailoutbox


@pytest.mark.django_db
class TestScheduleOnboardingEmails:
    def test_schedule_onboarding_emails__queues_every_stage_in_order(
        self, org, mailoutbox
    ):
        tasks.schedule_onboarding_emails.func(org_pk=org.pk)

        assert len(mailoutbox) == len(SEND_OFFSETS)
        assert mailoutbox[0].subject.startswith("You send 1,000")
        assert (
            mailoutbox[-1].subject
            == EMAIL_BY_STAGE[OnboardingStage.LAST_REMINDER].subject
        )

    def test_schedule_onboarding_emails__drops_a_missing_organization(
        self, org, mailoutbox
    ):
        tasks.schedule_onboarding_emails.func(org_pk=org.pk + 1)

        assert not mailoutbox

    def test_first_admin_schedules_the_sequence(
        self, user, mailoutbox, django_capture_on_commit_callbacks
    ):
        org = Organization.objects.create(slug="fresh-org", billing_is_active=True)

        with django_capture_on_commit_callbacks(execute=True):
            Membership.objects.create(
                org=org,
                user=user,
                role=Membership.Role.ADMIN,
            )

        assert len(mailoutbox) == len(SEND_OFFSETS)

    def test_second_admin_does_not_schedule_again(
        self, user, other_user, mailoutbox, django_capture_on_commit_callbacks
    ):
        org = Organization.objects.create(slug="team-org", billing_is_active=True)

        with django_capture_on_commit_callbacks(execute=True):
            Membership.objects.create(
                org=org,
                user=user,
                role=Membership.Role.ADMIN,
            )
        sent = len(mailoutbox)

        with django_capture_on_commit_callbacks(execute=True):
            Membership.objects.create(
                org=org,
                user=other_user,
                role=Membership.Role.ADMIN,
            )

        assert len(mailoutbox) == sent


def test_render_preview__fills_in_a_sample_organization_state_and_user():
    email = OnboardingWelcomeEmail.render_preview(language="en-us")

    assert email.org.slug == "acme"
    assert email.state["next_step"] == OnboardingStep.CREDENTIAL
    assert email.extra_context["user"].username == "jess"
    assert ">jess<" in email.html


@pytest.mark.django_db
class TestOnboardingEmail:
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

    def test_render_preview__keeps_the_callers_organization_state_and_user(
        self, org, user
    ):
        state = get_onboarding_state(org)

        email = OnboardingWelcomeEmail.render_preview(
            org=org,
            state=state,
            extra_context={"user": user},
            language="en-us",
        )

        assert email.org is org
