from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from abstract.admin import TimeStampedAdminMixin

from .models import MsaCredential, OutgoingMessage


@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    actions = ["release_spam_holds"]
    list_display = [
        "credential",
        "mail_from",
        "rcpt_to",
        "status",
        "created_at",
    ]
    list_filter = ["status", "credential__type"]
    list_select_related = ["credential"]
    search_fields = [
        "mail_from",
        "rcpt_to",
        "subject",
        "message_id",
    ]
    autocomplete_fields = ["org", "domain", "credential"]
    readonly_fields = ["id", "created_at"]

    @admin.action(
        permissions=["change"],
        description=_("Release selected spam holds"),
    )
    def release_spam_holds(self, request, queryset):
        if released := queryset.release():
            self.message_user(
                request,
                ngettext(
                    "Released %(count)d message.",
                    "Released %(count)d messages.",
                    released,
                )
                % {"count": released},
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _("No selected message was a held spam message."),
                messages.WARNING,
            )


@admin.register(MsaCredential)
class MsaCredentialAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "org",
        "key_prefix",
        "type",
        "name",
        "hold",
        "last_used_at",
    ]
    list_filter = ["type", "hold"]
    search_fields = ["org__name", "key_prefix", "name"]
    autocomplete_fields = ["org"]
    readonly_fields = ["key_hash", "key_prefix", "last_used_at"]
