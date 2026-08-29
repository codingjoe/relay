from email.message import EmailMessage

import pytest
from django.urls import reverse

from domains.models import Domain
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport


class TestFblReport:
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
        report, feedback_id = FblReport.parse_from_email(msg.as_bytes())
        assert report.feedback_type == "abuse"
        assert report.user_agent == "Gmail/FBL"
        assert report.original_mail_from == "sender@acme.com"
        assert feedback_id == ""

    def test_parse_from_email__raises_on_no_feedback(self):
        msg = EmailMessage()
        msg["Subject"] = "Not a report"
        msg.set_content("Regular email")
        with pytest.raises(ValueError):
            FblReport.parse_from_email(msg.as_bytes())

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

    @pytest.mark.django_db
    def test_get_absolute_url__reverses_to_detail(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="postmaster@acme.com",
        )
        report = FblReport.objects.create(
            org=org,
            domain=domain,
            message=message,
            reporting_org="gmail",
        )
        assert report.get_absolute_url() == reverse(
            "reputation:fbl-report-detail",
            kwargs={"org_slug": org.slug, "pk": report.pk},
        )

    def make_outgoing_message(self, org, **kwargs):
        defaults = {
            "org": org,
            "mail_from": "sender@acme.com",
            "rcpt_to": "rcpt@example.com",
            "status": OutgoingMessage.Status.HELD,
        }
        return OutgoingMessage.objects.create(**defaults | kwargs)

    @pytest.mark.django_db
    def test_create_for_spam__creates_report_with_spam_fields(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = self.make_outgoing_message(
            org,
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
        assert report.original_rcpt_to == "rcpt@example.com"
        assert report.original_message_id == "<abc@acme.com>"
        assert report.domain == domain
        assert report.org == org
        assert report.message == message

    @pytest.mark.django_db
    def test_create_for_spam__records_referenced_incoming_message(self, org, user):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="app.acme.com",
            mail_from="spam@acme.com",
            rcpt_to="inbox@relay.local",
            status=IncomingMessage.Status.QUARANTINED,
        )

        report = FblReport.create_for_spam(message)

        assert report is not None
        assert report.message == message
        assert report.source == "relay"
        assert report.original_rcpt_to == "inbox@relay.local"

    @pytest.mark.django_db
    def test_create_for_incoming__stores_provider_report(self, org, user):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="relay.local",
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@relay.local",
            status=IncomingMessage.Status.RECEIVED,
        )

        report = FblReport.create_for_incoming(message)

        assert report is not None
        assert report.source == "provider"
        assert report.org == org
        assert report.domain == domain
        assert report.message == message

    def test_parse_from_email__carries_feedback_id(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Feedback-ID: 9::aabbccddeeff001122334455:relay\n"
            b"Source-IP: 10.0.0.1\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )

        _, feedback_id = FblReport.parse_from_email(msg.as_bytes())

        assert feedback_id == "9::aabbccddeeff001122334455:relay"

    def test_parse_from_email__defaults_feedback_id_to_empty(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Source-IP: 10.0.0.1\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )

        _, feedback_id = FblReport.parse_from_email(msg.as_bytes())

        assert feedback_id == ""
