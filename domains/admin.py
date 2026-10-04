from django.contrib import admin
from unfold.admin import ModelAdmin

from abstract.admin import TimeStampedAdminMixin

from .models import Domain


@admin.register(Domain)
class DomainAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = [
        "name",
        "org",
        "verified_at",
        "nameserver_status",
        "spf_status",
        "dkim_rsa2048_status",
        "dkim_ed25519_status",
        "dmarc_status",
        "created_at",
    ]
    list_filter = [
        "nameserver_status",
        "spf_status",
        "dkim_rsa2048_status",
        "dkim_ed25519_status",
        "dmarc_status",
        "verified_at",
    ]
    search_fields = ["name", "org__name"]
    autocomplete_fields = ["org", "dkim_key_rsa2048", "dkim_key_ed25519"]
