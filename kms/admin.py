from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Certificate, OrgEncryptionKey, RecoveryEvent


@admin.register(Certificate)
class CertificateAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["subject", "issuer", "serial_number", "not_after", "created_at"]
    search_fields = ["fingerprint", "subject", "issuer"]
    readonly_fields = ["created_at", "modified_at"]


@admin.register(OrgEncryptionKey)
class OrgEncryptionKeyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "key_id", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["org__slug", "key_id"]


@admin.register(RecoveryEvent)
class RecoveryEventAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org_encryption_key", "triggered_by", "created_at"]
    search_fields = ["org_encryption_key__org__slug", "triggered_by__username"]
    readonly_fields = [
        "org_encryption_key",
        "triggered_by",
        "created_at",
        "modified_at",
    ]

    def has_delete_permission(self, request, obj=None):
        return False
