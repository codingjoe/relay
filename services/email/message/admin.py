from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Transmission


@admin.register(Transmission)
class TransmissionAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["message", "status", "code", "tls_mode", "created_at"]
    list_filter = ["status", "tls_mode"]
    search_fields = ["message__mail_from", "message__rcpt_to", "log_id"]
    readonly_fields = ["id", "created_at"]
