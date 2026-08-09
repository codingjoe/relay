import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email import message_from_bytes

ARF_FIELD_MAP = {
    "source-ip": "source_ip_address",
    "original-mail-from": "original_mail_from",
    "original-rcpt-to": "original_rcpt_to",
    "auth-failure": "authentication_results",
    "authentication-results": "authentication_results",
}
VALID_DELIVERY_RESULTS = frozenset({"delivered", "spam", "policy", "rejected", "other"})
MAX_DMARC_ELEMENT_MARKER_COUNT = 100_000
MAX_DMARC_RECORD_COUNT = 10_000


def parse_dmarc_xml(data):
    """Convert a DMARC aggregate report XML into a dict."""
    record_marker = b"<record" if isinstance(data, bytes) else "<record"
    element_marker = b"<" if isinstance(data, bytes) else "<"
    if data.count(element_marker) > MAX_DMARC_ELEMENT_MARKER_COUNT:
        raise ValueError("DMARC report contains too many elements.")
    if data.count(record_marker) > MAX_DMARC_RECORD_COUNT:
        raise ValueError("DMARC report contains too many records.")
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
    return datetime.fromtimestamp(int(value), tz=UTC) if value else None


def extract_part_text(part):
    """Extract text content from a MIME part, including sub-messages and base64 data."""
    import base64

    if not part.is_multipart():
        payload = part.get_payload(decode=True)
        if payload is not None:
            return payload.decode("utf-8", errors="replace")
        raw = part.get_payload()
        if isinstance(raw, str):
            return raw
        return ""
    # Handle message/* parts parsed as multipart by Python's email parser
    sub_parts = part.get_payload()
    if isinstance(sub_parts, list):
        for sub in sub_parts:
            payload = sub.get_payload(decode=True)
            if payload is None:
                raw = sub.get_payload()
                if isinstance(raw, str):
                    try:
                        payload = base64.b64decode(raw)
                    except ValueError, TypeError:
                        payload = raw.encode("utf-8", errors="replace")
            if payload is not None:
                # Python's email parser may return base64 bytes when CTE is set
                # but the sub-message structure doesn't honor it
                try:
                    stripped = bytes(payload).strip()
                    decoded = base64.b64decode(stripped)
                    re_encoded = base64.b64encode(decoded)
                    if re_encoded == stripped.replace(b"\n", b"").replace(b"\r", b""):
                        payload = decoded
                except ValueError, TypeError:
                    pass  # payload is not base64-encoded, use as-is
                return payload.decode("utf-8", errors="replace")
    return ""


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
        ct = part.get_content_type()
        match ct:
            case "message/feedback-report":
                body = extract_part_text(part)
                if body:
                    for line in body.splitlines():
                        if ":" in line:
                            key, value = (s.strip() for s in line.split(":", 1))
                            key_lower = key.lower()
                            if key_lower in ARF_FIELD_MAP:
                                report_data[ARF_FIELD_MAP[key_lower]] = value
                            elif key_lower == "arrival-date":
                                report_data["arrival_at"] = datetime.fromisoformat(
                                    value
                                )
                            elif key_lower == "delivery-result":
                                result = value.lower().replace(" ", "-")
                                if result in VALID_DELIVERY_RESULTS:
                                    report_data["delivery_result"] = result
            case "text/rfc822-headers" | "message/rfc822":
                body = extract_part_text(part)
                if body:
                    report_data["original_headers"] = body

    if not report_data["source_ip_address"] and not report_data["original_mail_from"]:
        raise ValueError("No ARF feedback-report content found.")
    return report_data
