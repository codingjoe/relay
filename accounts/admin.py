from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__name", "user__username"]
