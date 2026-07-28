from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import DmarcFailureReport, DmarcRecord, DmarcReport


@admin.register(DmarcReport)
class DmarcReportAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "report_id",
        "begin_at",
        "end_at",
        "report_status",
    ]
    list_filter = ["report_status", "domain"]
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


@admin.register(DmarcFailureReport)
class DmarcFailureReportAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "source_ip_address",
        "original_mail_from",
        "delivery_result",
        "report_status",
    ]
    list_filter = ["report_status", "delivery_result", "domain"]
    search_fields = [
        "reporting_org",
        "original_mail_from",
        "source_ip_address",
        "domain__name",
    ]
    readonly_fields = ["id", "arrival_at"]
