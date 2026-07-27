from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import DmarcRecord, DmarcReport, TlsFailure, TlsReport


@admin.register(DmarcReport)
class DmarcReportAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "report_id",
        "begin_at",
        "end_at",
        "status",
    ]
    list_filter = ["status", "domain"]
    search_fields = ["reporting_org", "report_id", "domain__name"]
    readonly_fields = ["id", "begin_at", "end_at", "reporting_org", "reporting_email"]


@admin.register(DmarcRecord)
class DmarcRecordAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "report",
        "source_ip_address",
        "count",
        "disposition",
        "dkim_alignment",
        "spf_alignment",
        "header_from",
    ]
    list_filter = ["disposition", "dkim_alignment", "spf_alignment"]
    search_fields = ["source_ip_address", "header_from", "report__report_id"]


@admin.register(TlsReport)
class TlsReportAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "report_id",
        "begin_at",
        "end_at",
        "successful_session_count",
        "failed_session_count",
        "status",
    ]
    list_filter = ["status", "domain"]
    search_fields = ["reporting_org", "report_id", "domain__name"]


@admin.register(TlsFailure)
class TlsFailureAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "report",
        "result_type",
        "sending_mta_ip_address",
        "receiving_mx_hostname",
        "count",
    ]
    list_filter = ["result_type", "policy_type"]
    search_fields = [
        "receiving_mx_hostname",
        "sending_mta_ip_address",
        "report__report_id",
    ]
