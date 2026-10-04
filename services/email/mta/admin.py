from django.contrib import admin
from unfold.admin import ModelAdmin

from abstract.admin import TimeStampedAdminMixin

from .models import (
    IncomingMessage,
    TlsFailure,
    TlsReport,
    Webhook,
    WebhookDelivery,
)


@admin.register(IncomingMessage)
class IncomingMessageAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = [
        "mail_from",
        "rcpt_to",
        "receiving_domain",
        "status",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["mail_from", "rcpt_to", "subject", "message_id"]
    autocomplete_fields = ["org", "domain"]
    readonly_fields = ["id", "created_at"]


@admin.register(Webhook)
class WebhookAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = ["org", "name", "url", "is_active", "last_used_at"]
    list_filter = ["is_active"]
    search_fields = ["org__slug", "name", "url"]
    autocomplete_fields = ["org", "domain", "signing_key"]
    readonly_fields = ["last_used_at"]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = [
        "webhook",
        "status",
        "is_test",
        "response_code",
        "created_at",
    ]
    list_filter = ["status", "is_test"]
    search_fields = ["webhook__url", "webhook__name"]
    autocomplete_fields = ["message", "webhook"]
    readonly_fields = ["id", "created_at"]


@admin.register(TlsReport)
class TlsReportAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "report_id",
        "begin_at",
        "end_at",
        "successful_session_count",
        "failed_session_count",
    ]
    search_fields = ["reporting_org", "report_id", "domain__name"]
    autocomplete_fields = ["org", "domain"]


@admin.register(TlsFailure)
class TlsFailureAdmin(TimeStampedAdminMixin, ModelAdmin):
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
    autocomplete_fields = ["report"]
