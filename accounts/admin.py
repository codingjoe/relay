from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["slug", "created_at", "reputation_locked"]
    search_fields = ["slug"]

    @admin.action(description=_("Unlock reputation"))
    def unlock_reputation(self, request, queryset):
        """Clear the sender-reputation lock on the selected organizations."""
        for org in queryset:
            org.reputation_locked = False
            org.reputation_locked_at = None
            org.save(
                update_fields=[
                    "reputation_locked",
                    "reputation_locked_at",
                    "modified_at",
                ]
            )

    actions = ["unlock_reputation"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__slug", "user__username"]
