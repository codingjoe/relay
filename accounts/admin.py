from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, MembershipEncryptionKey, Organization, UserEncryptionKey


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["slug", "created_at", "suspended_at"]
    search_fields = ["slug"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__slug", "user__username"]


@admin.register(UserEncryptionKey)
class UserEncryptionKeyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["user", "key_id", "created_at"]
    search_fields = ["user__username", "key_id"]


@admin.register(MembershipEncryptionKey)
class MembershipEncryptionKeyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["membership", "org_encryption_key", "created_at"]
    search_fields = ["membership__org__slug", "membership__user__username"]
