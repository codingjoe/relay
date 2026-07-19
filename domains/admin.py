from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Credential, Domain


@admin.register(Domain)
class DomainAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "owner",
        "verified_at",
        "nameserver_status",
        "dmarc_status",
        "created_at",
    ]
    list_filter = ["nameserver_status", "dmarc_status", "verified_at"]
    search_fields = ["name", "owner__username"]
    readonly_fields = [
        "verification_token",
    ]


@admin.register(Credential)
class CredentialAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["owner", "key", "type", "name", "hold", "last_used_at"]
    list_filter = ["type", "hold"]
    search_fields = ["owner__username", "key", "name"]
    readonly_fields = ["key", "last_used_at"]
