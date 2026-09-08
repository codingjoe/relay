from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import Organization
from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.handlers import process_incoming_message
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport
from services.email.reputation.tasks import parse_fbl_report, resolve_fbl_owner


def make_arf_email(
    feedback_type="fraud",
    original_mail_from="sender@acme.com",
    feedback_id=None,
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
    if feedback_id:
        report += f"Feedback-ID: {feedback_id}\n"
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


def make_report(org, raw_bytes):
    domain = Domain.objects.create(name="fbl.example", org=org)
    message = IncomingMessage.objects.create(
        org=org,
        domain=domain,
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

    def test_parse_fbl_report__does_not_attribute_by_domain(self, org):
        sender_org = Organization.objects.create(slug="sender")
        Domain.objects.create(name="sender.test", org=sender_org)
        report = make_report(
            org, make_arf_email(original_mail_from="someone@sender.test")
        )

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.org == org
        # Unattributed reports keep the receiving domain; the sender's
        # "sender.test" domain must not claim the report.
        assert report.domain == report.message.domain

    def test_parse_fbl_report__keeps_receiving_org_when_unroutable(self, org):
        report = make_report(org, make_arf_email())

        parse_fbl_report.func(report_pk=report.pk)

        report.refresh_from_db()
        assert report.org == org

    def test_parse_fbl_report__routes_report_by_feedback_id(self, org):
        sender_org = Organization.objects.create(slug="sender")
        domain = Domain.objects.create(name="sender.test", org=sender_org)
        OutgoingMessage.objects.create(
            org=sender_org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
            feedback_id="9999::aabbccddeeff001122334455:relay",
        )
        report = make_report(
            org,
            make_arf_email(
                original_headers=(
                    b"From: sender@acme.com\r\n"
                    b"Feedback-ID: 9999::aabbccddeeff001122334455:relay\r\n"
                ),
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


@pytest.mark.django_db
class TestResolveFblOwner:
    def test_resolve_fbl_owner__attributes_by_feedback_id(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
            feedback_id="9999::aabbccddeeff001122334455:relay",
        )

        assert resolve_fbl_owner("9999::aabbccddeeff001122334455:relay") == (
            org,
            domain,
        )

    def test_resolve_fbl_owner__rejects_case_shifted_feedback_id(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
            feedback_id="9999::aabbccddeeff001122334455:relay",
        )

        assert resolve_fbl_owner("9999::AABBCCDDEEFF001122334455:RELAY") is None

    def test_resolve_fbl_owner__returns_none_for_unknown_feedback_id(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
            feedback_id="9999::aabbccddeeff001122334455:relay",
        )

        assert resolve_fbl_owner("9999::0000000000000000000000:relay") is None

    def test_resolve_fbl_owner__never_matches_empty_feedback_id_claim(self, org):
        domain = Domain.objects.create(name="sender.test", org=org)
        OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="sender@sender.test",
            rcpt_to="rcpt@gmail.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("sent.eml", b"body"),
            feedback_id="",
        )

        with CaptureQueriesContext(connection) as queries:
            resolved = resolve_fbl_owner("")

        assert resolved is None
        assert not queries.captured_queries


class TestProcessIncomingMessage:
    @pytest.mark.django_db(transaction=True)
    async def test_process_incoming_message__fbl_recipient_creates_report(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDERS = ["feedback@gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "feedback@gmail.com",
                "fbl@example.com",
                make_arf_email(),
                {"ssl_object": None},
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
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDERS = ["feedback@gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam") as spam_task:
            result = await process_incoming_message(
                "forged@example.org",
                "fbl@example.com",
                make_arf_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        assert await IncomingMessage.objects.aexists()
        spam_task.enqueue.assert_called_once()
