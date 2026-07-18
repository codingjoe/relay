from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Message, Transmission


@admin.register(Message)
class MessageAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "sender",
        "scope",
        "mail_from",
        "rcpt_to",
        "status",
        "received_at",
    ]
    list_filter = ["scope", "status"]
    search_fields = [
        "mail_from",
        "rcpt_to",
        "subject",
        "message_id",
        "sender__username",
    ]
    readonly_fields = [
        "id",
        "received_at",
    ]
    date_hierarchy = "received_at"


@admin.register(Transmission)
class TransmissionAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["message", "status", "code", "created_at"]
    list_filter = ["status"]
    search_fields = ["message__mail_from", "message__rcpt_to", "log_id"]
    readonly_fields = ["id", "created_at"]
