from email.message import EmailMessage

from services.email.reputation.models import FblReport


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
        try:
            FblReport.parse_from_email(msg.as_bytes())
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestFblReportProperties:
    def test_status_badge_variant__is_destructive(self):
        report = FblReport()
        assert report.status_badge_variant == "destructive"
