from contextlib import suppress
from datetime import datetime
from email import message_from_bytes

from abnf import ParseError
from abnf.grammars.rfc5322 import Rule

from abstract.email_utils import extract_part_text

FIELD_NAME_RULE = Rule("field-name")
MAX_FIELD_NAME_LENGTH = 255

FBL_FIELD_MAP = {
    "source-ip": "source_ip_address",
    "original-mail-from": "original_mail_from",
    "original-rcpt-to": "original_rcpt_to",
    "auth-failure": "authentication_results",
    "authentication-results": "authentication_results",
    "original-message-id": "original_message_id",
    "user-agent": "user_agent",
    "version": "version",
    "feedback-id": "feedback_id",
}
VALID_FEEDBACK_TYPES = frozenset(
    {"abuse", "fraud", "virus", "not-spam", "other", "opt-out"}
)


class NoArfFeedbackError(ValueError):
    """The message contains no ARF feedback-report content."""


def parse_fbl(raw_bytes):
    """
    Return the report fields of an ARF (RFC 5965) message as a dict.

    Feedback-Type defaults to "abuse" when absent or unrecognized, and
    Feedback-ID falls back to the echoed original message headers, stripped
    of all whitespace either way. Raises `NoArfFeedbackError` if the message
    contains no feedback-report content.
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
        "feedback_id": "",
    }

    for part in msg.walk():
        match part.get_content_type():
            case "message/feedback-report":
                if body := extract_part_text(part):
                    apply_fbl_fields(report_data, parse_feedback_fields(body))
            case "text/rfc822-headers" | "message/rfc822":
                if body := extract_part_text(part):
                    report_data["original_headers"] = body

    if not report_data["feedback_id"] and report_data["original_headers"]:
        echoed = message_from_bytes(report_data["original_headers"].encode())
        report_data["feedback_id"] = echoed.get("Feedback-ID", "")
    report_data["feedback_id"] = "".join(report_data["feedback_id"].split())

    if not report_data["source_ip_address"] and not report_data["original_mail_from"]:
        raise NoArfFeedbackError
    return report_data


def parse_feedback_fields(body):
    """
    Parse a feedback-report body into lowercase field names and values.

    Continuation (obs-fold) lines join the preceding value with a single
    space, the last occurrence of a repeated field wins, and lines that are
    neither a continuation nor a valid field name (overlong names included)
    are ignored and end any continuation in progress.
    """
    fields: dict[str, list[str]] = {}
    key = None
    for line in body.splitlines():
        if line.startswith((" ", "\t")):
            if key is not None and (continuation := line.strip()):
                fields[key].append(continuation)
        elif ":" in line:
            name, _, value = line.partition(":")
            name = name.strip()
            if len(name) > MAX_FIELD_NAME_LENGTH:
                key = None
            else:
                try:
                    FIELD_NAME_RULE.parse_all(name)
                except ParseError:
                    key = None
                else:
                    key = name.lower()
                    fields[key] = [value.strip()]
        else:
            key = None
    return {key: " ".join(parts) for key, parts in fields.items()}


def apply_fbl_fields(report_data, fields):
    """Map the parsed feedback-report fields onto the report dict."""
    for key, value in fields.items():
        match key:
            case "feedback-type":
                feedback_type = value.lower().replace(" ", "-")
                if feedback_type in VALID_FEEDBACK_TYPES:
                    report_data["feedback_type"] = feedback_type
            case "arrival-date":
                with suppress(ValueError):
                    report_data["arrival_at"] = datetime.fromisoformat(value)
            case _ if key in FBL_FIELD_MAP:
                report_data[FBL_FIELD_MAP[key]] = value
