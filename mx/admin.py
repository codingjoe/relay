from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import IncomingMessage, Webhook, WebhookDelivery


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
