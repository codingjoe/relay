from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import (
    IncomingMessage,
    MtaStsPolicy,
    TlsFailure,
    TlsReport,
    Webhook,
    WebhookDelivery,
)


@admin.register(IncomingMessage)
class IncomingMessageAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "mail_from",
        "rcpt_to",
        "receiving_domain",
        "status",
        "received_with_tls",
        "received_at",
    ]
    list_filter = ["status", "received_with_tls"]
    search_fields = ["mail_from", "rcpt_to", "subject", "message_id"]
    readonly_fields = ["id", "received_at"]


@admin.register(Webhook)
class WebhookAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "name", "url", "is_active", "last_used_at"]
    list_filter = ["is_active"]
    search_fields = ["org__slug", "name", "url"]
    readonly_fields = ["last_used_at"]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "webhook",
        "status",
        "is_test",
        "response_code",
        "created_at",
    ]
    list_filter = ["status", "is_test"]
    search_fields = ["webhook__url", "webhook__name"]
    readonly_fields = ["id", "created_at"]


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


@admin.register(MtaStsPolicy)
class MtaStsPolicyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["domain", "status", "mode", "policy_id", "checked_at"]
    list_filter = ["status", "mode"]
    search_fields = ["domain", "policy_id"]
    readonly_fields = ["id", "modified_at", "created_at"]
