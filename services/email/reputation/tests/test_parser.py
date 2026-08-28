from datetime import UTC, datetime
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

    def test_parse_fbl__raises_on_empty_feedback_report_body(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(b"", maintype="message", subtype="feedback-report")
        with pytest.raises(ValueError):
            parse_fbl(msg.as_bytes())

    def test_parse_fbl__joins_obs_fold_continuation_with_single_space(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Authentication-Results: spf=pass\n"
            b"  dkim=fail\n"
            b"\tdmarc=none\n"
            b"Source-IP: 10.0.0.1\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["authentication_results"] == "spf=pass dkim=fail dmarc=none"
        assert result["source_ip_address"] == "10.0.0.1"

    def test_parse_fbl__drops_orphan_fold_continuation(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"  orphan continuation\nSource-IP: 10.0.0.1\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1"

    def test_parse_fbl__drops_fold_after_garbage_line(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\n"
            b"garbage line without colon\n"
            b"  dropped continuation\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1"
        assert result["original_mail_from"] == "sender@acme.com"

    def test_parse_fbl__resets_fold_anchor_on_garbage_line(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\n"
            b"  joined continuation\n"
            b"garbage line without colon\n"
            b"  dropped continuation\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1 joined continuation"
        assert result["original_mail_from"] == "sender@acme.com"

    def test_parse_fbl__skips_whitespace_only_continuation_line(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\n"
            b" \t \n"
            b"  joined continuation\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1 joined continuation"

    def test_parse_fbl__skips_invalid_field_name_and_resets_fold_anchor(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\n"
            b"Source IP: 10.0.0.2\n"
            b"  dropped continuation\n"
            b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1"
        assert result["original_mail_from"] == "sender@acme.com"

    def test_parse_fbl__skips_overlong_field_name_and_resets_fold_anchor(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Original-Mail-From: sender@acme.com\n"
            + b"X" * 256
            + b": injected value\n"
            + b"  dropped continuation\n"
            + b"Source-IP: 10.0.0.1\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["original_mail_from"] == "sender@acme.com"
        assert result["source_ip_address"] == "10.0.0.1"

    def test_parse_fbl__accepts_field_name_at_max_length(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\n"
            + b"X" * 255
            + b": injected value\n"
            + b"  consumed continuation\n"
            + b"Original-Mail-From: sender@acme.com\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.1"
        assert result["original_mail_from"] == "sender@acme.com"

    def test_parse_fbl__keeps_last_occurrence_of_duplicate_field(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Source-IP: 10.0.0.1\nSource-IP: 10.0.0.2\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["source_ip_address"] == "10.0.0.2"

    def test_parse_fbl__keeps_default_feedback_type_when_unrecognized(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: bogus\nSource-IP: 10.0.0.9\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "abuse"

    def test_parse_fbl__normalizes_feedback_type_spaces_to_dashes(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: Not Spam\nSource-IP: 10.0.0.8\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["feedback_type"] == "not-spam"

    def test_parse_fbl__parses_valid_arrival_date(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Arrival-Date: 2025-01-15T10:30:00Z\n"
            b"Source-IP: 10.0.0.7\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["arrival_at"] == datetime(2025, 1, 15, 10, 30, tzinfo=UTC)

    def test_parse_fbl__defaults_reporting_org_to_empty_without_from_header(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\nSource-IP: 10.0.0.6\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["reporting_org"] == ""
        assert result["reporting_email"] == ""

    def test_parse_fbl__extracts_original_headers_from_message_rfc822_part(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\nSource-IP: 10.0.0.5\n",
            maintype="message",
            subtype="feedback-report",
        )
        msg.add_attachment(
            b"From: sender@acme.com\r\nTo: recipient@gmail.com\r\n",
            maintype="message",
            subtype="rfc822",
        )
        result = parse_fbl(msg.as_bytes())
        assert "From: sender@acme.com" in result["original_headers"]
        assert "To: recipient@gmail.com" in result["original_headers"]

    def test_parse_fbl__maps_authentication_results_field(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\n"
            b"Authentication-Results: dkim=pass\n"
            b"Source-IP: 10.0.0.3\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["authentication_results"] == "dkim=pass"

    def test_parse_fbl__maps_auth_failure_alias_to_authentication_results(self):
        msg = EmailMessage()
        msg["Subject"] = "FBL Report"
        msg["From"] = "feedback@gmail.com"
        msg.set_content("Complaint")
        msg.add_attachment(
            b"Feedback-Type: abuse\nAuth-Failure: spf=fail\nSource-IP: 10.0.0.4\n",
            maintype="message",
            subtype="feedback-report",
        )
        result = parse_fbl(msg.as_bytes())
        assert result["authentication_results"] == "spf=fail"
