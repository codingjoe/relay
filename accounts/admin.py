from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization, UserPreference


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "slug",
        "created_at",
        "suspended_at",
        "billing_is_active",
        "is_free",
    ]
    search_fields = ["slug"]
    list_filter = ["billing_is_active", "is_free"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__slug", "user__username"]
    autocomplete_fields = ["org", "user"]


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "time_zone"]
    search_fields = ["user__username", "time_zone"]
    autocomplete_fields = ["user"]
