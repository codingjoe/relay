from django.contrib import admin
from unfold.admin import ModelAdmin

from abstract.admin import TimeStampedAdminMixin

from .models import MsaCredential, OutgoingMessage


@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = [
        "credential",
        "mail_from",
        "rcpt_to",
        "status",
        "created_at",
    ]
    list_filter = ["status", "credential__type"]
    search_fields = [
        "mail_from",
        "rcpt_to",
        "subject",
        "message_id",
    ]
    autocomplete_fields = ["org", "domain", "credential"]
    readonly_fields = ["id", "created_at"]


@admin.register(MsaCredential)
class MsaCredentialAdmin(TimeStampedAdminMixin, ModelAdmin):
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
    autocomplete_fields = ["org"]
    readonly_fields = ["key_hash", "key_prefix", "last_used_at"]
