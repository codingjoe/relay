from email.message import EmailMessage

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from domains.models import Domain
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport


def make_arf_report_email():
    message = EmailMessage()
    message["From"] = "spam@acme.com"
    message["To"] = "victim@example.com"
    message["Subject"] = "Buy now"
    message.set_content("Spam body")
    return message.as_bytes()


class TestFblReportParseFromEmail:
    def test_parse_from_email__returns_fbl_report(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"User-Agent: Gmail/FBL\n"
            b"Version: 1\n"
            b"Source-IP: 10.0.0.1\n"
            b"Original-Mail-From: sender@acme.com\n"
            b"Original-Rcpt-To: recipient@gmail.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        report = FblReport.parse_from_email(msg.as_bytes())
        assert report.feedback_type == "abuse"
        assert report.user_agent == "Gmail/FBL"
        assert report.original_mail_from == "sender@acme.com"

    def test_parse_from_email__raises_on_no_feedback(self):
        msg = EmailMessage()
        msg["Subject"] = "Not a report"
        msg.set_content("Regular email")
        with pytest.raises(ValueError):
            FblReport.parse_from_email(msg.as_bytes())


class TestFblReportProperties:
    def test_status_badge_variant__is_destructive(self):
        report = FblReport()
        assert report.status_badge_variant == "destructive"

    def test_str__with_domain(self):
        report = FblReport(
            domain=Domain(name="acme.com"),
            reporting_org="gmail",
            original_mail_from="sender@acme.com",
        )
        assert str(report) == "gmail → acme.com (sender@acme.com)"

    def test_str__without_domain(self):
        report = FblReport(
            reporting_org="gmail",
            original_mail_from="sender@acme.com",
        )
        assert str(report) == "gmail → ? (sender@acme.com)"


@pytest.mark.django_db
class TestFblReportGetAbsoluteUrl:
    def test_get_absolute_url__reverses_to_detail(self, org):
        report = FblReport.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
        )
        assert report.get_absolute_url() == reverse(
            "reputation:fbl-report-detail",
            kwargs={"org_slug": org.slug, "pk": report.pk},
        )


class TestFblReportCreateForSpamWithoutDomain:
    def test_create_for_spam__returns_none_without_domain(self):
        message = IncomingMessage(
            mail_from="spam@example.com",
            rcpt_to="rcpt@example.com",
        )
        result = FblReport.create_for_spam(message)
        assert result is None


@pytest.mark.django_db
class TestFblReportCreateForSpam:
    def make_outgoing_message(self, org, raw_bytes=None, **kwargs):
        defaults = {
            "org": org,
            "mail_from": "sender@acme.com",
            "rcpt_to": "rcpt@example.com",
            "status": OutgoingMessage.Status.HELD,
        }
        if raw_bytes is not None:
            defaults["raw_body"] = SimpleUploadedFile("test.eml", raw_bytes)
        return OutgoingMessage.objects.create(**defaults | kwargs)

    def test_create_for_spam__creates_report_with_spam_fields(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_outgoing_message(
            org,
            raw_bytes=b"spam content",
            subject="Spam subject",
            message_id="<abc@acme.com>",
            domain=domain,
        )

        report = FblReport.create_for_spam(message)
        assert report is not None
        assert report.source == "relay"
        assert report.feedback_type == "abuse"
        assert report.user_agent == "relay"
        assert report.original_mail_from == "sender@acme.com"
        assert report.domain == domain
        assert report.org == org

    def test_create_for_spam__without_raw_body_stores_empty_file(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_outgoing_message(org, domain=domain)

        report = FblReport.create_for_spam(message)

        assert report is not None
        assert report.raw_body.read() == b""

    def test_create_for_spam__records_receiving_domain_of_incoming_message(
        self, org, user
    ):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="app.acme.com",
            mail_from="spam@acme.com",
            rcpt_to="inbox@relay.local",
            status=IncomingMessage.Status.QUARANTINED,
            raw_body=SimpleUploadedFile("test.eml", b"spam"),
        )

        report = FblReport.create_for_spam(message)

        assert report is not None
        assert report.receiving_domain == "app.acme.com"
        assert report.original_rcpt_to == "inbox@relay.local"


@pytest.mark.django_db
class TestFblReportSendFblReport:
    def make_quarantined_message(self, org, domain, raw_bytes=None):
        defaults = {
            "org": org,
            "domain": domain,
            "receiving_domain": "example.com",
            "mail_from": "spam@acme.com",
            "rcpt_to": "victim@example.com",
            "status": IncomingMessage.Status.QUARANTINED,
        }
        if raw_bytes is not None:
            defaults["raw_body"] = SimpleUploadedFile("quarantined.eml", raw_bytes)
        return IncomingMessage.objects.create(**defaults)

    def test_send_fbl_report__skips_when_no_reporting_address(
        self, org, mailoutbox, settings
    ):
        settings.RELAY_FBL_REPORTING_ADDRESS = ""
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_quarantined_message(org, domain)

        FblReport.send_fbl_report(message)

        assert mailoutbox == []

    def test_send_fbl_report__sends_arf_with_original_headers(
        self, org, mailoutbox, settings
    ):
        settings.RELAY_FBL_REPORTING_ADDRESS = "fbl@relay.local"
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_quarantined_message(
            org, domain, raw_bytes=make_arf_report_email()
        )

        FblReport.send_fbl_report(message)

        assert len(mailoutbox) == 1
        email = mailoutbox[0]
        assert email.to == ["fbl@relay.local"]
        assert email.subject == "FBL report for acme.com"
        assert email.from_email == (
            f"{settings.RELAY_FBL_LOCAL_PART}@{settings.RELAY_PLATFORM_DOMAIN}"
        )
        mime = email.message()
        assert mime.get_content_type() == "multipart/report"
        assert mime.get_param("report-type") == "feedback-loop"
        text_part, feedback_part, headers_part = mime.get_payload()
        assert text_part.get_content_type() == "text/plain"
        assert feedback_part.get_content_type() == "message/feedback-report"
        assert "Feedback-Type: abuse" in feedback_part.get_payload()
        assert "Original-Mail-From: spam@acme.com" in feedback_part.get_payload()
        assert headers_part.get_content_type() == "text/rfc822-headers"
        assert "Subject: Buy now" in headers_part.get_payload()

    def test_send_fbl_report__without_raw_body_omits_original_headers(
        self, org, mailoutbox, settings
    ):
        settings.RELAY_FBL_REPORTING_ADDRESS = "fbl@relay.local"
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_quarantined_message(org, domain)

        FblReport.send_fbl_report(message)

        assert len(mailoutbox) == 1
        _, feedback_part, headers_part = mailoutbox[0].message().get_payload()
        assert "Feedback-Type: abuse" in feedback_part.get_payload()
        assert "Subject: Buy now" not in headers_part.get_payload()
