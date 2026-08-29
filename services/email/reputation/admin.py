from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import FblReport


@admin.register(FblReport)
class FblReportAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = [
        "reporting_org",
        "domain",
        "feedback_type",
        "source_ip_address",
        "original_mail_from",
        "arrival_at",
    ]
    list_filter = ["feedback_type"]
    search_fields = [
        "reporting_org",
        "original_mail_from",
        "original_message_id",
        "source_ip_address",
        "domain__name",
    ]
    readonly_fields = ["id", "arrival_at"]
