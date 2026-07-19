from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import SmtpCredential


@admin.register(SmtpCredential)
class SmtpCredentialAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "organization",
        "key_prefix",
        "type",
        "name",
        "hold",
        "last_used_at",
    ]
    list_filter = ["type", "hold"]
    search_fields = ["organization__name", "key_prefix", "name"]
    readonly_fields = ["key_hash", "key_prefix", "last_used_at"]
