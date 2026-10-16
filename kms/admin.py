from django.contrib import admin

from abstract.admin import TimeStampedAdminMixin

from .models import Certificate, SigningKey


@admin.register(SigningKey)
class SigningKeyAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["key_id", "algorithm", "created_at"]
    list_filter = ["algorithm"]
    search_fields = ["key_id", "algorithm"]
    readonly_fields = ["key_id", "algorithm", "encrypted_private_key", "public_key"]

    def has_add_permission(self, request):
        return False


@admin.register(Certificate)
class CertificateAdmin(TimeStampedAdminMixin, admin.ModelAdmin):
    list_display = ["subject", "issuer", "serial_number", "not_after", "created_at"]
    search_fields = ["fingerprint", "subject", "issuer"]
    autocomplete_fields = ["issuer_certificate"]
    readonly_fields = ["created_at", "modified_at"]
