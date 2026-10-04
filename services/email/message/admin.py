from django.contrib import admin
from unfold.admin import ModelAdmin

from abstract.admin import TimeStampedAdminMixin

from .models import Message, Transmission


@admin.register(Message)
class MessageAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = ["mail_from", "rcpt_to", "subject", "created_at"]
    search_fields = ["mail_from", "rcpt_to", "subject", "message_id"]
    autocomplete_fields = ["org", "domain"]
    readonly_fields = ["id", "created_at"]


@admin.register(Transmission)
class TransmissionAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = ["message", "status", "code", "tls_mode", "created_at"]
    list_filter = ["status", "tls_mode"]
    search_fields = ["message__mail_from", "message__rcpt_to"]
    autocomplete_fields = ["message", "tls_certificate"]
    readonly_fields = ["id", "created_at"]
