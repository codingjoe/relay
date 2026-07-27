from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import OutgoingMessage, SmtpCredential, Transmission


@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "sender",
        "mail_from",
        "rcpt_to",
        "credential",
        "status",
        "received_at",
    ]
    list_filter = ["status", "credential__type"]
    search_fields = [
        "mail_from",
        "rcpt_to",
        "subject",
        "message_id",
        "sender__username",
    ]
    readonly_fields = ["id", "received_at"]


@admin.register(Transmission)
class TransmissionAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["message", "status", "code", "created_at"]
    list_filter = ["status"]
    search_fields = ["message__mail_from", "message__rcpt_to", "log_id"]
    readonly_fields = ["id", "created_at"]


@admin.register(SmtpCredential)
class SmtpCredentialAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "org",
        "key_prefix",
        "type",
        "name",
        "hold",
        "last_used_at",
    ]
    list_filter = ["type", "hold"]
    search_fields = ["org__name", "key_prefix", "name"]
    readonly_fields = ["key_hash", "key_prefix", "last_used_at"]
