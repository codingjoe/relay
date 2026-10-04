from django.contrib import admin
from unfold.admin import ModelAdmin

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = ["slug", "created_at", "suspended_at", "billing_is_active"]
    search_fields = ["slug"]
    list_filter = ["billing_is_active"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__slug", "user__username"]
    autocomplete_fields = ["org", "user"]
