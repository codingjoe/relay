from email.message import EmailMessage

import pytest
from django.conf import settings
from django.core.files.base import ContentFile

from accounts.models import Organization
from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.reputation.models import FblReport
from services.email.reputation.tasks import parse_fbl_report


def make_arf_email(feedback_type="fraud"):
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
        "Original-Mail-From: sender@acme.com\n"
        "Original-Rcpt-To: victim@gmail.com\n"
    )
    message.add_attachment(
        report.encode(),
        maintype="message",
        subtype="feedback-report",
    )
    return message.as_bytes()


def make_report(org, raw_bytes):
    report = FblReport(
        org=org,
        mail_from="feedback@gmail.com",
        rcpt_to="fbl@acme.com",
    )
    report.raw_body.save("report.eml", ContentFile(raw_bytes), save=False)
    report.save(force_insert=True)
    return report


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
        message = OutgoingMessage(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@gmail.com",
            domain=domain,
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("sent.eml", ContentFile(b"body"), save=False)
        message.save(force_insert=True)
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


class TestFblReportIngress:
    @pytest.mark.django_db(transaction=True)
    async def test_fbl_recipient__creates_and_parses_report(self, org):
        from services.email.mta.handlers import process_incoming_message
        from services.email.mta.models import IncomingMessage

        domain = Domain.objects.create(name="example.com", org=org)
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
        assert report.mail_from == "feedback@gmail.com"
        assert report.domain == domain
        assert report.receiving_domain == "example.com"
        assert report.received_with_tls is True
        assert report.feedback_type == "fraud"
        assert report.original_mail_from == "sender@acme.com"
