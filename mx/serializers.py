"""DRF serializers for parsing TLS-RPT JSON reports (RFC 8460)."""

from rest_framework import serializers


class TlsReportDateRangeSerializer(serializers.Serializer):
    """Date range within a TLS-RPT report."""

    start_datetime = serializers.DateTimeField(source="start-datetime", required=False)
    end_datetime = serializers.DateTimeField(source="end-datetime", required=False)


class TlsFailureDetailSerializer(serializers.Serializer):
    """A single TLS failure record within a TLS-RPT report."""

    result_type = serializers.CharField(source="result-type", default="other")
    sending_mta_ip_address = serializers.CharField(
        source="sending-mta-ip", required=False, allow_blank=True
    )
    receiving_mx_hostname = serializers.CharField(
        source="receiving-mx-hostname", required=False, allow_blank=True
    )
    receiving_mx_ip_address = serializers.CharField(
        source="receiving-mx-ip", required=False, allow_null=True
    )
    count = serializers.IntegerField(source="failed-session-count", default=0)
    additional_info = serializers.CharField(
        source="additional-information",
        required=False,
        allow_blank=True,
        default="",
    )


class TlsPolicySerializer(serializers.Serializer):
    """Policy metadata within a TLS-RPT report."""

    policy_type = serializers.CharField(source="policy-type", default="sts")
    policy_domain = serializers.CharField(
        source="policy-domain", required=False, allow_blank=True, default=""
    )


class TlsPolicySummarySerializer(serializers.Serializer):
    """Session count summary for a policy."""

    successful_session_count = serializers.IntegerField(
        source="successful-session-count", default=0
    )
    failed_session_count = serializers.IntegerField(
        source="failed-session-count", default=0
    )


class TlsPolicyEntrySerializer(serializers.Serializer):
    """A policy entry with its summary and failure details."""

    policy = TlsPolicySerializer(required=False, default=dict)
    summary = TlsPolicySummarySerializer(required=False, default=dict)
    failure_details = TlsFailureDetailSerializer(
        source="failure-details", many=True, default=list
    )


class TlsReportSerializer(serializers.Serializer):
    """Top-level TLS-RPT report (RFC 8460)."""

    organization_name = serializers.CharField(source="organization-name", default="")
    contact_info = serializers.CharField(source="contact-info", default="")
    report_id = serializers.CharField(source="report-id", default="")
    date_range = TlsReportDateRangeSerializer(
        source="date-range", required=False, default=dict
    )
    policies = TlsPolicyEntrySerializer(many=True, default=list)

    @property
    def metadata(self):
        """Extract report metadata from validated data."""
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
        """Extract policy data with failures from validated data."""
        policies = []
        for entry in self.validated_data.get("policies", []):
            policy = entry.get("policy", {})
            summary = entry.get("summary", {})
            failures = []
            for fd in entry.get("failure_details", []):
                failures.append(
                    {
                        "result_type": fd.get("result_type", "other"),
                        "sending_mta_ip_address": fd.get("sending_mta_ip_address", ""),
                        "receiving_mx_hostname": fd.get("receiving_mx_hostname", ""),
                        "receiving_mx_ip_address": fd.get("receiving_mx_ip_address"),
                        "count": fd.get("count", 0),
                        "additional_info": fd.get("additional_info", ""),
                    }
                )
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
