import logging
from email.message import EmailMessage
from unittest.mock import patch

import pytest
from crontask import scheduler
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail.backends import locmem
from django.utils import timezone
from django_letter.notifications import hash_email
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership, Organization
from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage
from services.email.msa.tasks import mint_bounce_address
from services.email.mta.handlers import process_incoming_message
from services.email.mta.models import IncomingMessage
from services.email.mta.tests.conftest import make_dmarc_evaluation
from services.email.reputation.evaluation import compute_org_reputation
from services.email.reputation.models import FblReport
from services.email.reputation.tasks import (
    create_provider_fbl_report,
    parse_fbl_report,
    send_org_weekly_digest,
    send_weekly_digests,
)


def make_arf_email(
    feedback_type="fraud",
    original_mail_from="sender@acme.com",
    original_headers=None,
):
    message = EmailMessage()
    message["From"] = "feedback@gmail.com"
    message["Subject"] = "FBL Report"
    message.set_content("Complaint")
    report = (
        f"Feedback-Type: {feedback_type}\n"
        "User-Agent: Gmail/FBL\n"
        "Version: 1.0\n"
        "Arrival-Date: 2026-01-02T03:04:05Z\n"
        "Source-IP: 192.0.2.1\n"
        f"Original-Mail-From: {original_mail_from}\n"
        "Original-Rcpt-To: victim@gmail.com\n"
    )
    message.add_attachment(
        report.encode(),
        maintype="message",
        subtype="feedback-report",
    )
    if original_headers is not None:
        message.add_attachment(
            original_headers, maintype="text", subtype="rfc822-headers"
        )
    return message.as_bytes()


def make_outgoing_message(org, domain):
    return OutgoingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="sender@acme.com",
        rcpt_to="rcpt@example.com",
        status=OutgoingMessage.Status.SENT,
    )


def make_report(org, raw_bytes, complained_message=None):
    """Store a provider report the way ingestion does."""
    domain = Domain.objects.create(name="fbl.example", org=org)
    message = IncomingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="feedback@gmail.com",
        rcpt_to="fbl@acme.com",
        raw_body=SimpleUploadedFile("report.eml", raw_bytes),
    )
    if complained_message is None:
        complained_message = make_outgoing_message(org, domain)
    return FblReport.create_for_incoming(message, complained_message)


def make_report_email(org, domain, raw_bytes):
    return IncomingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="feedback@gmail.com",
        rcpt_to="fbl@acme.com",
        raw_body=SimpleUploadedFile("report.eml", raw_bytes),
    )


REFUSED_ADDRESS = "bob@example.com"  # the other_user fixture's address


class RefusedConnectionError(OSError):
    """A refused connection, the way a dead SMTP host raises it."""


class RefusedEmailBackend(locmem.EmailBackend):
    """Refuse one address the way a dead SMTP host would."""

    def send_messages(self, email_messages):
        for message in email_messages:
            if REFUSED_ADDRESS in message.to:
                raise RefusedConnectionError
        return super().send_messages(email_messages)


@pytest.mark.django_db
class TestParseFblReport:
    def test_parse_fbl_report__updates_report_fields(self, org):
        report = make_report(org, make_arf_email())

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.feedback_type == "fraud"
        assert report.user_agent == "Gmail/FBL"
        assert report.version == "1.0"
        assert report.reporting_org == "feedback@gmail.com"
        assert report.reporting_email == "feedback@gmail.com"
        assert str(report.source_ip_address) == "192.0.2.1"
        assert report.original_mail_from == "sender@acme.com"
        assert report.original_rcpt_to == "victim@gmail.com"
        assert Organization.objects.get(pk=org.pk).suspended_at is None

    def test_parse_fbl_report__leaves_non_arf_report_unparsed(self, org):
        report = make_report(org, b"Not an ARF email")

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.feedback_type == FblReport.FeedbackType.ABUSE

    def test_parse_fbl_report__checks_org_reputation(
        self, org, user, settings, mailoutbox
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@gmail.com",
            domain=domain,
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )
        Transmission.objects.create(
            message=message,
            code=550,
            status=Transmission.Status.BOUNCED,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        report = make_report(org, make_arf_email())

        parse_fbl_report.func(report_pk=report.pk)

        org.refresh_from_db()
        assert org.suspended_at is not None
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["alice@example.com"]


@pytest.mark.django_db
class TestCreateProviderFblReport:
    def test_create_provider_fbl_report__stores_report_for_the_named_message(self, org):
        sender_org = Organization.objects.create(slug="sender")
        domain = Domain.objects.create(name="sender.test", org=sender_org)
        original = make_outgoing_message(sender_org, domain)
        report_email = make_report_email(
            org,
            Domain.objects.create(name="fbl.example", org=org),
            make_arf_email(original_mail_from=mint_bounce_address(original)),
        )

        create_provider_fbl_report.func(message_pk=str(report_email.pk))

        report = FblReport.objects.get(message=report_email)
        assert report.org == sender_org
        assert report.domain == domain
        assert report.complained_message_id == original.pk
        report_email.refresh_from_db()
        assert report_email.org == sender_org
        assert report_email.domain == domain

    def test_create_provider_fbl_report__stores_nothing_without_a_named_message(
        self, org
    ):
        sender_org = Organization.objects.create(slug="sender")
        Domain.objects.create(name="sender.test", org=sender_org)
        report_email = make_report_email(
            org,
            Domain.objects.create(name="fbl.example", org=org),
            make_arf_email(original_mail_from="someone@sender.test"),
        )

        create_provider_fbl_report.func(message_pk=str(report_email.pk))

        assert not FblReport.objects.exists()
        assert IncomingMessage.objects.filter(pk=report_email.pk).exists()

    def test_create_provider_fbl_report__stores_nothing_for_an_echoed_feedback_id(
        self, org
    ):
        report_email = make_report_email(
            org,
            Domain.objects.create(name="fbl.example", org=org),
            make_arf_email(
                original_headers=(
                    b"From: sender@acme.com\r\n"
                    b"Feedback-ID: 9999::aabbccddeeff001122334455:relay\r\n"
                ),
            ),
        )

        create_provider_fbl_report.func(message_pk=str(report_email.pk))

        assert not FblReport.objects.exists()
        assert IncomingMessage.objects.filter(pk=report_email.pk).exists()

    def test_create_provider_fbl_report__stores_nothing_for_a_non_arf_email(self, org):
        report_email = make_report_email(
            org,
            Domain.objects.create(name="fbl.example", org=org),
            b"Not an ARF email",
        )

        create_provider_fbl_report.func(message_pk=str(report_email.pk))

        assert not FblReport.objects.exists()

    def test_create_provider_fbl_report__counts_one_complaint_per_named_message(
        self, org
    ):
        sender_org = Organization.objects.create(slug="sender")
        domain = Domain.objects.create(name="sender.test", org=sender_org)
        original = make_outgoing_message(sender_org, domain)
        return_path = mint_bounce_address(original)
        fbl_domain = Domain.objects.create(name="fbl.example", org=org)
        for _index in range(2):
            report_email = make_report_email(
                org, fbl_domain, make_arf_email(original_mail_from=return_path)
            )
            create_provider_fbl_report.func(message_pk=str(report_email.pk))

        assert FblReport.objects.count() == 2
        assert set(
            FblReport.objects.values_list("complained_message_id", flat=True)
        ) == {original.pk}
        assert compute_org_reputation(sender_org)["complaints"] == 1


class TestProcessIncomingMessage:
    @pytest.mark.django_db(transaction=True)
    async def test_process_incoming_message__fbl_recipient_creates_report(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain)
        return_path = mint_bounce_address(original)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "feedback@arf.mail.yahoo.com",
                "fbl@example.com",
                make_arf_email(original_mail_from=return_path),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(header_from="arf.mail.yahoo.com"),
                "",
            )

        assert result == "250 OK"
        report = await FblReport.objects.aget(org=org)
        assert report.source == "provider"
        assert report.domain == domain
        assert report.feedback_type == "fraud"
        assert report.original_mail_from == return_path

    @pytest.mark.django_db(transaction=True)
    async def test_process_incoming_message__fbl_recipient_unknown_sender_checks_spam(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam") as spam_task:
            result = await process_incoming_message(
                "forged@example.org",
                "fbl@example.com",
                make_arf_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        assert await IncomingMessage.objects.aexists()
        spam_task.enqueue.assert_called_once()


@pytest.mark.django_db
class TestSendOrgWeeklyDigest:
    def test_send_org_weekly_digest__mails_each_member(
        self, org, user, other_user, mailoutbox
    ):
        Membership.objects.create(org=org, user=other_user)
        OutgoingMessage.objects.create(
            org=org,
            domain=Domain.objects.create(name="acme.com", org=org),
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )

        send_org_weekly_digest.func(org_id=org.pk)

        assert sorted(message.to[0] for message in mailoutbox) == [
            "alice@example.com",
            "bob@example.com",
        ]
        assert {message.subject for message in mailoutbox} == {
            "test-org sent one message out the door"
        }

    def test_send_org_weekly_digest__skips_a_disabled_member(
        self, org, user, other_user, mailoutbox
    ):
        Membership.objects.create(org=org, user=other_user)
        NotificationPreference.objects.create(
            email_hash=hash_email(user.email),
            slug="weekly-digest",
            enabled=False,
        )

        send_org_weekly_digest.func(org_id=org.pk)

        assert [message.to[0] for message in mailoutbox] == ["bob@example.com"]

    def test_send_org_weekly_digest__drops_a_suspended_organization(
        self, org, mailoutbox, caplog
    ):
        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at"])

        with caplog.at_level(logging.INFO, logger="services.email.reputation.tasks"):
            send_org_weekly_digest.func(org_id=org.pk)

        assert mailoutbox == []
        assert (
            f"Dropped the weekly digest for suspended organization {org.pk!r}"
            in caplog.messages
        )

    def test_send_org_weekly_digest__skips_the_member_the_mailer_refuses(
        self, org, user, other_user, mailoutbox, settings, caplog
    ):
        Membership.objects.create(org=org, user=other_user)
        settings.MAILERS = {
            "default": {
                "BACKEND": "services.email.reputation.tests.test_tasks.RefusedEmailBackend"
            }
        }

        with caplog.at_level(logging.ERROR, logger="services.email.reputation.tasks"):
            send_org_weekly_digest.func(org_id=org.pk)

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]
        assert f"Weekly digest for user {other_user.pk!r} failed" in caplog.messages


class TestSendWeeklyDigestSchedule:
    def test_send_weekly_digests__runs_on_monday_morning(self):
        job = next(
            job for job in scheduler.get_jobs() if job.name == send_weekly_digests.name
        )
        fields = {field.name: str(field) for field in job.trigger.fields}

        assert fields["day_of_week"] == "mon"
        assert fields["hour"] == "8"
        assert fields["minute"] == "0"


@pytest.mark.django_db
class TestSendWeeklyDigests:
    def test_send_weekly_digests__queues_one_task_per_active_organization(
        self, org, user, write_org, mailoutbox
    ):
        suspended = Organization.objects.create(
            slug="suspended-org", suspended_at=timezone.now()
        )
        Membership.objects.create(org=suspended, user=user)

        send_weekly_digests.func()

        assert sorted(message.subject for message in mailoutbox) == [
            "other-org sent 0 messages out the door",
            "test-org sent 0 messages out the door",
        ]
