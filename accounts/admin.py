from django.contrib import admin
from social_django.models import Association, Nonce, UserSocialAuth

from abstract.admin import TimeStampedAdminMixin

from .models import Membership, Organization


@admin.register(UserSocialAuth)
class UserSocialAuthAdmin(admin.ModelAdmin):
    """Like social_django's admin, but with the deprecated list_select_related fixed."""

    list_display = ("user", "id", "provider", "uid", "created", "modified")
    list_filter = ("provider",)
    raw_id_fields = ("user",)
    readonly_fields = ("created", "modified")
    list_select_related = ("user",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )


@admin.register(Nonce)
class NonceAdmin(admin.ModelAdmin):
    list_display = ("id", "server_url", "timestamp", "salt")
    search_fields = ("server_url",)


@admin.register(Association)
class AssociationAdmin(admin.ModelAdmin):
    list_display = ("id", "server_url", "assoc_type")
    list_filter = ("assoc_type",)
    search_fields = ("server_url",)


@admin.register(Organization)
class OrganizationAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["slug", "created_at"]
    search_fields = ["slug"]


@admin.register(Membership)
class MembershipAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "user", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["org__slug", "user__username"]
