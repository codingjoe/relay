import contextlib
import datetime
import xml.etree.ElementTree as ET
from email import message_from_bytes

from abstract.email_utils import extract_part_text

ARF_FIELD_MAP = {
    "source-ip": "source_ip_address",
    "original-mail-from": "original_mail_from",
    "original-rcpt-to": "original_rcpt_to",
    "auth-failure": "authentication_results",
    "authentication-results": "authentication_results",
}
VALID_DELIVERY_RESULTS = frozenset({"delivered", "spam", "policy", "rejected", "other"})


class NoArfFeedbackError(ValueError):
    """The message contains no ARF feedback-report content."""


def parse_dmarc_xml(data):
    """Convert a DMARC aggregate report XML into a dict."""
    root = ET.fromstring(data)

    metadata_elem = root.find("report_metadata")
    metadata = {
        "reporting_org": text(metadata_elem, "org_name"),
        "reporting_email": text(metadata_elem, "email"),
        "report_id": text(metadata_elem, "report_id"),
        "begin_at": parse_timestamp(metadata_elem, "date_range/begin"),
        "end_at": parse_timestamp(metadata_elem, "date_range/end"),
    }

    records = []
    for record_elem in root.findall("record"):
        row = record_elem.find("row")
        policy_eval = row.find("policy_evaluated") if row is not None else None
        identifiers = record_elem.find("identifiers")
        auth_results = record_elem.find("auth_results")
        dkim_result_elem = (
            auth_results.find("dkim") if auth_results is not None else None
        )
        spf_result_elem = auth_results.find("spf") if auth_results is not None else None
        records.append(
            {
                "source_ip_address": text(row, "source_ip"),
                "count": int(text(row, "count") or "0"),
                "disposition": text(policy_eval, "disposition") or "none",
                "dkim_alignment": text(policy_eval, "dkim") or "fail",
                "spf_alignment": text(policy_eval, "spf") or "fail",
                "header_from": text(identifiers, "header_from"),
                "envelope_from": text(identifiers, "envelope_from"),
                "dkim_domain": text(dkim_result_elem, "domain"),
                "dkim_result": text(dkim_result_elem, "result") or "none",
                "spf_domain": text(spf_result_elem, "domain"),
                "spf_result": text(spf_result_elem, "result") or "none",
            }
        )

    return {"metadata": metadata, "records": records}


def text(parent, path):
    """Return stripped text from an XML element at the given XPath, or empty string."""
    elem = parent.find(path) if parent is not None else None
    return elem.text.strip() if elem is not None and elem.text else ""


def parse_timestamp(parent, path):
    """Convert a Unix timestamp from an XML element into an aware datetime."""
    value = text(parent, path)
    return (
        datetime.datetime.fromtimestamp(int(value), tz=datetime.UTC) if value else None
    )


def parse_arf(raw_bytes):
    """Return the parsed ARF (Abuse Reporting Format) DMARC RUF report as a dict."""
    msg = message_from_bytes(raw_bytes)
    report_data = {
        "reporting_org": msg.get("From", ""),
        "reporting_email": msg.get("From", ""),
        "source_ip_address": "",
        "arrival_at": None,
        "original_mail_from": "",
        "original_rcpt_to": "",
        "authentication_results": "",
        "delivery_result": "other",
        "original_headers": "",
    }

    for part in msg.walk():
        match part.get_content_type():
            case "message/feedback-report":
                if body := extract_part_text(part):
                    update_arf_report(report_data, body)
            case "text/rfc822-headers" | "message/rfc822":
                if body := extract_part_text(part):
                    report_data["original_headers"] = body

    if not report_data["source_ip_address"] and not report_data["original_mail_from"]:
        raise NoArfFeedbackError
    return report_data


def update_arf_report(report_data, body):
    """Map the feedback-report body fields onto the report dict."""
    for line in body.splitlines():
        if ":" in line:
            key, value = (s.strip() for s in line.split(":", 1))
            match key.lower():
                case key_lower if key_lower in ARF_FIELD_MAP:
                    report_data[ARF_FIELD_MAP[key_lower]] = value
                case "arrival-date":
                    with contextlib.suppress(ValueError):
                        report_data["arrival_at"] = datetime.datetime.fromisoformat(
                            value
                        )
                case "delivery-result":
                    result = value.lower().replace(" ", "-")
                    if result in VALID_DELIVERY_RESULTS:
                        report_data["delivery_result"] = result
