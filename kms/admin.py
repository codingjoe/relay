from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Certificate


@admin.register(Certificate)
class CertificateAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["subject", "issuer", "serial_number", "not_after", "created_at"]
    search_fields = ["fingerprint", "subject", "issuer"]
    readonly_fields = ["created_at", "modified_at"]
