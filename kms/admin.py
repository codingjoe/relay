from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import OrgEncryptionKey, RecoveryEvent, SigningKey


@admin.register(SigningKey)
class SigningKeyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["algorithm", "key_id", "created_at"]
    list_filter = ["algorithm"]
    search_fields = ["key_id"]


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
