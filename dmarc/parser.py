"""Parse DMARC aggregate (XML) and TLS-RPT (JSON) report emails."""

import gzip
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from email import message_from_bytes


def extract_attachment(raw_bytes):
    """Extract and decompress the report attachment from a raw email.

    DMARC reports arrive as gzip- or zip-compressed XML; TLS-RPT reports
    as gzip- or zip-compressed JSON. Returns the decompressed bytes, or
    ``None`` if no attachment is found.
    """
    msg = message_from_bytes(raw_bytes)
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        data = part.get_payload(decode=True)
        if data is None:
            continue
        filename = part.get_filename() or ""
        content_type = part.get_content_type()
        if filename.endswith(".gz") or content_type == "application/gzip":
            data = gzip.decompress(data)
        elif filename.endswith(".zip") or content_type == "application/zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                data = zf.read(zf.namelist()[0])
        return data
    return None


def parse_dmarc_xml(data):
    """Parse a DMARC aggregate report XML into a dict.

    Returns ``{"metadata": {...}, "records": [...]}`` where each record is
    ``{"source_ip_address": ..., "count": ..., "disposition": ...,
    "dkim_alignment": ..., "spf_alignment": ..., "header_from": ...,
    "envelope_from": ..., "dkim_domain": ..., "dkim_result": ...,
    "spf_domain": ..., "spf_result": ...}``.
    """
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
    """Get stripped text from an XML element at the given XPath, or empty string."""
    if parent is None:
        return ""
    elem = parent.find(path)
    return elem.text.strip() if elem is not None and elem.text else ""


def parse_timestamp(parent, path):
    """Parse a Unix timestamp from an XML element into an aware datetime."""
    value = text(parent, path)
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def parse_arf(raw_bytes):
    """Parse an ARF (Abuse Reporting Format) DMARC RUF report.

    Returns a dict with the report metadata, or raises ``ValueError``.
    """
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
        if part.is_multipart():
            continue
        content_type = part.get_content_type()

        match content_type:
            case "message/feedback-report":
                payload = part.get_payload(decode=True)
                if payload:
                    text = payload.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        if ":" not in line:
                            continue
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        match key:
                            case "source-ip":
                                report_data["source_ip_address"] = value
                            case "original-mail-from":
                                report_data["original_mail_from"] = value
                            case "original-rcpt-to":
                                report_data["original_rcpt_to"] = value
                            case "arrival-date":
                                report_data["arrival_at"] = datetime.fromisoformat(
                                    value
                                )
                            case "auth-failure" | "authentication-results":
                                report_data["authentication_results"] = value
                            case "delivery-result":
                                result = value.lower().replace(" ", "-")
                                if result in {
                                    "delivered",
                                    "spam",
                                    "policy",
                                    "rejected",
                                    "other",
                                }:
                                    report_data["delivery_result"] = result

            case "text/rfc822-headers" | "message/rfc822":
                payload = part.get_payload(decode=True)
                if payload:
                    report_data["original_headers"] = payload.decode(
                        "utf-8", errors="replace"
                    )

    if not report_data["source_ip_address"] and not report_data["original_mail_from"]:
        raise ValueError("No ARF feedback-report content found.")
    return report_data
