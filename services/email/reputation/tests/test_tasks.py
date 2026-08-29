import uuid
from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Organization
from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.handlers import process_incoming_message
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport
from services.email.reputation.tasks import parse_fbl_report, resolve_fbl_owner


def make_arf_email(feedback_type="fraud", original_mail_from="sender@acme.com"):
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
    return message.as_bytes()


def make_report(org, raw_bytes):
    message = IncomingMessage.objects.create(
        org=org,
        mail_from="feedback@gmail.com",
        rcpt_to="fbl@acme.com",
        raw_body=SimpleUploadedFile("report.eml", raw_bytes),
    )
    return FblReport.create_for_incoming(message)


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
        )
        report = make_report(org, make_arf_email())

        parse_fbl_report.func(report_pk=report.pk)

        org.refresh_from_db()
        assert org.suspended_at is not None
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["alice@example.com"]

    def test_parse_fbl_report__routes_report_by_envelope_sender_token(self, org):
        sender_org = Organization.objects.create(slug="sender")
        domain = Domain.objects.create(name="sender.test", org=sender_org)
        original = OutgoingMessage.objects.create(
            org=sender_org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )
        report = make_report(
            org,
            make_arf_email(
                original_mail_from=(
                    f"{settings.RELAY_BOUNCE_LOCAL_PART}+{original.pk}"
                    f"@{domain.sender_domain}"
                )
            ),
        )

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.org == sender_org
        assert report.domain == domain
        message = report.message
        message.refresh_from_db()
        assert message.org == sender_org
        assert message.domain == domain

    def test_parse_fbl_report__does_not_attribute_by_domain(self, org):
        sender_org = Organization.objects.create(slug="sender")
        Domain.objects.create(name="sender.test", org=sender_org)
        report = make_report(
            org, make_arf_email(original_mail_from="someone@sender.test")
        )

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.org == org
        assert report.domain is None

    def test_parse_fbl_report__keeps_receiving_org_when_unroutable(self, org):
        report = make_report(org, make_arf_email())

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.org == org


@pytest.mark.django_db
class TestResolveFblOwner:
    def test_resolve_fbl_owner__returns_org_and_domain_from_token(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        original = OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )

        assert resolve_fbl_owner(
            f"{settings.RELAY_BOUNCE_LOCAL_PART}+{original.pk}@{domain.sender_domain}"
        ) == (org, domain)

    def test_resolve_fbl_owner__rejects_mismatched_return_path(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        original = OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )

        assert (
            resolve_fbl_owner(
                f"{settings.RELAY_BOUNCE_LOCAL_PART}+{original.pk}@evil.test"
            )
            is None
        )

    def test_resolve_fbl_owner__returns_none_without_domain(self, org):
        original = OutgoingMessage.objects.create(
            org=org,
            domain=None,
            mail_from="sender@example.com",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
        )

        assert (
            resolve_fbl_owner(
                f"{settings.RELAY_BOUNCE_LOCAL_PART}+{original.pk}@anything.test"
            )
            is None
        )

    def test_resolve_fbl_owner__returns_none_without_token(self, org):
        Domain.objects.create(name="sender.test", org=org)

        assert resolve_fbl_owner("someone@sender.test") is None

    def test_resolve_fbl_owner__returns_none_for_unknown_token(self, org):
        token = uuid.uuid4()

        assert resolve_fbl_owner(f"bounce+{token}@sender.test") is None

    def test_resolve_fbl_owner__returns_none_for_malformed_token(self, org):
        assert resolve_fbl_owner("bounce+not-a-uuid@sender.test") is None


class TestProcessIncomingMessage:
    @pytest.mark.django_db(transaction=True)
    async def test_process_incoming_message__fbl_recipient_creates_report(
        self, org, settings
    ):
        settings.RELAY_PLATFORM_DOMAIN = "example.com"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        with (
            patch(
                "services.email.mta.models.is_spf_pass",
                return_value=True,
            ),
            patch("services.email.mta.handlers.check_incoming_spam"),
        ):
            result = await process_incoming_message(
                "feedback@gmail.com",
                f"{settings.RELAY_FBL_LOCAL_PART}@example.com",
                make_arf_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        assert result == "250 OK"
        report = await FblReport.objects.aget(org=org)
        assert report.source == "provider"
        assert report.domain == domain
        assert report.feedback_type == "fraud"
        assert report.original_mail_from == "sender@acme.com"

    @pytest.mark.django_db(transaction=True)
    async def test_process_incoming_message__fbl_recipient_unknown_sender_checks_spam(
        self, org, settings
    ):
        settings.RELAY_PLATFORM_DOMAIN = "example.com"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam") as spam_task:
            result = await process_incoming_message(
                "forged@example.org",
                f"{settings.RELAY_FBL_LOCAL_PART}@example.com",
                make_arf_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        assert await IncomingMessage.objects.aexists()
        spam_task.enqueue.assert_called_once()
