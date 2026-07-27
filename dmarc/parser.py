"""Parse DMARC aggregate (XML) and TLS-RPT (JSON) report emails."""

import gzip
import io
import json
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


def parse_tls_json(data):
    """Parse a TLS-RPT JSON report into a dict.

    Returns ``{"metadata": {...}, "policies": [...]}`` where each policy is
    ``{"policy_type": ..., "policy_domain": ..., "successful_session_count": ...,
    "failed_session_count": ..., "failures": [...]}``.
    """
    report = json.loads(data)

    date_range = report.get("date-range", {})
    metadata = {
        "reporting_org": report.get("organization-name", ""),
        "reporting_email": report.get("contact-info", ""),
        "report_id": report.get("report-id", ""),
        "begin_at": parse_iso_datetime(date_range.get("start-datetime")),
        "end_at": parse_iso_datetime(date_range.get("end-datetime")),
    }

    policies = []
    for policy_entry in report.get("policies", []):
        policy = policy_entry.get("policy", {})
        summary = policy_entry.get("summary", {})
        failures = []
        for fd in policy_entry.get("failure-details", []):
            failures.append(
                {
                    "result_type": fd.get("result-type", "other"),
                    "sending_mta_ip_address": fd.get("sending-mta-ip", ""),
                    "receiving_mx_hostname": fd.get("receiving-mx-hostname", ""),
                    "receiving_mx_ip_address": fd.get("receiving-mx-ip"),
                    "count": int(fd.get("failed-session-count", 0)),
                    "additional_info": fd.get("additional-information", ""),
                }
            )
        policies.append(
            {
                "policy_type": policy.get("policy-type", "sts"),
                "policy_domain": policy.get("policy-domain", ""),
                "successful_session_count": int(
                    summary.get("successful-session-count", 0)
                ),
                "failed_session_count": int(summary.get("failed-session-count", 0)),
                "failures": failures,
            }
        )

    return {"metadata": metadata, "policies": policies}


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


def parse_iso_datetime(value):
    """Parse an ISO 8601 datetime string into an aware datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value)
