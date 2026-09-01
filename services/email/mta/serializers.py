"""DRF serializers for parsing TLS-RPT JSON reports (RFC 8460)."""

import json

from rest_framework import serializers


def snake_case_keys(value):
    """
    Recursively convert dashed TLS-RPT keys to snake_case field names.

    RFC 8460 uses dashed key names ("organization-name"), while DRF looks up
    incoming data by field name, not by `source`.
    """
    if isinstance(value, list):
        return [snake_case_keys(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {key.replace("-", "_"): snake_case_keys(item) for key, item in value.items()}


class TlsReportDateRangeSerializer(serializers.Serializer):
    """Date range within a TLS-RPT report."""

    start_datetime = serializers.DateTimeField(required=False)
    end_datetime = serializers.DateTimeField(required=False)


class TlsFailureDetailSerializer(serializers.Serializer):
    """TLS failure record within a TLS-RPT report."""

    result_type = serializers.CharField(default="other")
    sending_mta_ip = serializers.CharField(required=False, allow_blank=True)
    receiving_mx_hostname = serializers.CharField(required=False, allow_blank=True)
    receiving_mx_ip = serializers.CharField(required=False, allow_null=True)
    failed_session_count = serializers.IntegerField(default=0)
    additional_information = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class TlsPolicySerializer(serializers.Serializer):
    """Policy metadata within a TLS-RPT report."""

    policy_type = serializers.CharField(default="sts")
    policy_domain = serializers.CharField(required=False, allow_blank=True, default="")


class TlsPolicySummarySerializer(serializers.Serializer):
    """Session count summary for a policy."""

    successful_session_count = serializers.IntegerField(default=0)
    failed_session_count = serializers.IntegerField(default=0)


class TlsPolicyEntrySerializer(serializers.Serializer):
    """Policy entry with its summary and failure details."""

    policy = TlsPolicySerializer(required=False, default=dict)
    summary = TlsPolicySummarySerializer(required=False, default=dict)
    failure_details = TlsFailureDetailSerializer(many=True, default=list)


class TlsReportSerializer(serializers.Serializer):
    """Top-level TLS-RPT report (RFC 8460)."""

    organization_name = serializers.CharField(default="")
    contact_info = serializers.CharField(default="")
    report_id = serializers.CharField(default="")
    date_range = TlsReportDateRangeSerializer(required=False, default=dict)
    policies = TlsPolicyEntrySerializer(many=True, default=list)

    @property
    def metadata(self):
        """Return report metadata from validated data."""
        validated = self.validated_data
        date_range = validated.get("date_range", {})
        return {
            "reporting_org": validated.get("organization_name", ""),
            "reporting_email": validated.get("contact_info", ""),
            "report_id": validated.get("report_id", ""),
            "begin_at": date_range.get("start_datetime"),
            "end_at": date_range.get("end_datetime"),
        }

    @property
    def parsed_policies(self):
        """Return policy data with failures from validated data."""
        policies = []
        for entry in self.validated_data.get("policies", []):
            policy = entry.get("policy", {})
            summary = entry.get("summary", {})
            failures = [
                {
                    "result_type": detail.get("result_type", "other"),
                    "sending_mta_ip_address": detail.get("sending_mta_ip", ""),
                    "receiving_mx_hostname": detail.get("receiving_mx_hostname", ""),
                    "receiving_mx_ip_address": detail.get("receiving_mx_ip"),
                    "count": detail.get("failed_session_count", 0),
                    "additional_info": detail.get("additional_information", ""),
                }
                for detail in entry.get("failure_details", [])
            ]
            policies.append(
                {
                    "policy_type": policy.get("policy_type", "sts"),
                    "policy_domain": policy.get("policy_domain", ""),
                    "successful_session_count": summary.get(
                        "successful_session_count", 0
                    ),
                    "failed_session_count": summary.get("failed_session_count", 0),
                    "failures": failures,
                }
            )
        return policies

    @classmethod
    def parse_json(cls, data):
        """Return metadata and policies from a TLS-RPT JSON byte string."""
        serializer = cls(data=snake_case_keys(json.loads(data)))
        serializer.is_valid(raise_exception=True)
        return serializer.metadata, serializer.parsed_policies
