"""Parse TLS-RPT JSON reports (RFC 8460)."""

import json

from django.utils import dateparse, timezone


def snake_case_keys(value):
    """
    Recursively convert dashed TLS-RPT keys to snake_case field names.

    RFC 8460 uses dashed key names ("organization-name").
    """
    if isinstance(value, list):
        return [snake_case_keys(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {key.replace("-", "_"): snake_case_keys(item) for key, item in value.items()}


def parse_datetime(value):
    """Return an aware datetime from an RFC 3339 string, or None."""
    parsed = dateparse.parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def parse_tls_report(data):
    """
    Return report metadata and policy summaries from a TLS-RPT JSON byte string.

    Missing fields fall back to the RFC 8460 defaults.
    """
    report = snake_case_keys(json.loads(data))
    date_range = report.get("date_range") or {}
    metadata = {
        "reporting_org": report.get("organization_name", ""),
        "reporting_email": report.get("contact_info", ""),
        "report_id": report.get("report_id", ""),
        "begin_at": parse_datetime(date_range.get("start_datetime")),
        "end_at": parse_datetime(date_range.get("end_datetime")),
    }
    policies = []
    for entry in report.get("policies", []):
        policy = entry.get("policy") or {}
        summary = entry.get("summary") or {}
        policies.append(
            {
                "policy_type": policy.get("policy_type", "sts"),
                "policy_domain": policy.get("policy_domain", ""),
                "successful_session_count": summary.get("successful_session_count", 0),
                "failed_session_count": summary.get("failed_session_count", 0),
                "failures": [
                    {
                        "result_type": detail.get("result_type", "other"),
                        "sending_mta_ip_address": detail.get("sending_mta_ip", ""),
                        "receiving_mx_hostname": detail.get(
                            "receiving_mx_hostname", ""
                        ),
                        "receiving_mx_ip_address": detail.get("receiving_mx_ip"),
                        "count": detail.get("failed_session_count", 0),
                        "additional_info": detail.get("additional_information", ""),
                    }
                    for detail in entry.get("failure_details", [])
                ],
            }
        )
    return metadata, policies
