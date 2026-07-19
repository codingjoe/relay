from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Domain


@admin.register(Domain)
class DomainAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "organization",
        "verified_at",
        "nameserver_status",
        "dmarc_status",
        "created_at",
    ]
    list_filter = ["nameserver_status", "dmarc_status", "verified_at"]
    search_fields = ["name", "organization__name"]
    readonly_fields = ["verification_token"]
