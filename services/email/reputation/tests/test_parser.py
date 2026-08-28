from email.message import EmailMessage

import pytest

from services.email.reputation.parser import parse_fbl


class TestParseFbl:
    def test_parse_fbl__raises_on_no_feedback_report(self):
        msg = EmailMessage()
        msg["Subject"] = "Not a report"
        msg.set_content("Just a regular email")
        with pytest.raises(ValueError):
            parse_fbl(msg.as_bytes())

    def test_parse_fbl__extracts_abuse_complaint(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("This is a complaint report")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"User-Agent: Gmail/FBL\n"
            b"Version: 1\n"
            b"Source-IP: 10.0.0.1\n"
            b"Original-Mail-From: sender@acme.com\n"
            b"Original-Rcpt-To: recipient@gmail.com\n"
            b"Original-Message-ID: <abc123@acme.com>\n"
            b"Arrival-Date: 2025-01-15T10:30:00Z\n"
            b"Authentication-Results: spf=pass dkim=pass\n",
            maintype="message",
            subtype="feedback-report",
        )
        msg.add_attachment(
            b"From: sender@acme.com\r\nTo: recipient@gmail.com\r\n",
            maintype="text",
            subtype="rfc822-headers",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "abuse"
        assert result["user_agent"] == "Gmail/FBL"
        assert result["version"] == "1"
        assert result["source_ip_address"] == "10.0.0.1"
        assert result["original_mail_from"] == "sender@acme.com"
        assert result["original_rcpt_to"] == "recipient@gmail.com"
        assert result["original_message_id"] == "<abc123@acme.com>"
        assert result["arrival_at"] is not None
        assert "From: sender@acme.com" in result["original_headers"]

    def test_parse_fbl__defaults_to_abuse_when_no_feedback_type(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@yahoo.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.2\nOriginal-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "abuse"

    def test_parse_fbl__extracts_fraud_type(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@outlook.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: fraud\nOriginal-Mail-From: spammer@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "fraud"

    def test_parse_fbl__reports_org_from_from_header(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL"
        msg["From"] = "complaints@verizon.com"
        msg.set_content("Report body")
        msg.add_attachment(
            b"Feedback-Type: abuse\nOriginal-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["reporting_org"] == "complaints@verizon.com"
        assert result["reporting_email"] == "complaints@verizon.com"

    def test_parse_fbl__ignores_invalid_arrival_date(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Arrival-Date: not-a-date\n"
            b"Source-IP: 10.0.0.3\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["arrival_at"] is None
        assert result["source_ip_address"] == "10.0.0.3"

    def test_parse_fbl__skips_empty_and_unparseable_parts(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(b"", maintype="message", subtype="feedback-report")
        msg.add_attachment(
            b"not a header line\n"
            b"Incident-Name: spam\n"
            b"Feedback-Type: nonsense\n"
            b"Feedback-Type: abuse\n"
            b"Source-IP: 10.0.0.4\n",
            maintype="message",
            subtype="feedback-report",
        )
        msg.add_attachment(b"", maintype="text", subtype="rfc822-headers")
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "abuse"
        assert result["source_ip_address"] == "10.0.0.4"
        assert result["original_headers"] == ""
