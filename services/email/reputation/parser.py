from datetime import datetime
from email import message_from_bytes

from abstract.email_utils import extract_part_text

FBL_FIELD_MAP = {
    "source-ip": "source_ip_address",
    "original-mail-from": "original_mail_from",
    "original-rcpt-to": "original_rcpt_to",
    "auth-failure": "authentication_results",
    "authentication-results": "authentication_results",
    "original-message-id": "original_message_id",
    "user-agent": "user_agent",
    "version": "version",
}
VALID_FEEDBACK_TYPES = frozenset(
    {"abuse", "fraud", "virus", "not-spam", "other", "opt-out"}
)


def parse_fbl(raw_bytes):
    """Return FBL (Feedback Loop) complaint report fields as a dict.

    The report uses the ARF (Abuse Reporting Format, RFC 5965) MIME structure.
    Raises `ValueError` if no ARF feedback-report content is found.
    """
    msg = message_from_bytes(raw_bytes)
    report_data = {
        "feedback_type": "abuse",
        "user_agent": "",
        "version": "",
        "reporting_org": msg.get("From", ""),
        "reporting_email": msg.get("From", ""),
        "source_ip_address": "",
        "arrival_at": None,
        "original_mail_from": "",
        "original_rcpt_to": "",
        "original_message_id": "",
        "authentication_results": "",
        "original_headers": "",
    }

    for part in msg.walk():
        match part.get_content_type():
            case "message/feedback-report":
                body = extract_part_text(part)
                if body:
                    for line in body.splitlines():
                        if ":" in line:
                            key, value = (s.strip() for s in line.split(":", 1))
                            key_lower = key.lower()
                            if key_lower == "feedback-type":
                                ftype = value.lower().replace(" ", "-")
                                if ftype in VALID_FEEDBACK_TYPES:
                                    report_data["feedback_type"] = ftype
                            elif key_lower == "arrival-date":
                                try:
                                    report_data["arrival_at"] = datetime.fromisoformat(
                                        value
                                    )
                                except ValueError:
                                    pass
                            elif key_lower in FBL_FIELD_MAP:
                                report_data[FBL_FIELD_MAP[key_lower]] = value
            case "text/rfc822-headers" | "message/rfc822":
                body = extract_part_text(part)
                if body:
                    report_data["original_headers"] = body

    if not report_data["source_ip_address"] and not report_data["original_mail_from"]:
        raise ValueError("No ARF feedback-report content found.")
    return report_data
