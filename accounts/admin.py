from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["name", "slug", "is_personal", "created_at"]
    list_filter = ["is_personal"]
    search_fields = ["name", "slug"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["organization", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["organization__name", "user__username"]
