from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import OnboardingCampaign


@admin.register(OnboardingCampaign)
class OnboardingCampaignAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["org", "stage", "next_send_at", "sent_count"]
    search_fields = ["org__slug"]
    autocomplete_fields = ["org"]
