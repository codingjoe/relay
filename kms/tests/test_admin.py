from django.contrib import admin

from kms.admin import SigningKeyAdmin
from kms.models import SigningKey


class TestSigningKeyAdmin:
    def test_signing_key_admin__registered(self):
        assert isinstance(admin.site._registry[SigningKey], SigningKeyAdmin)

    def test_signing_key_admin__readonly_key_material(self):
        assert "encrypted_private_key" in SigningKeyAdmin.readonly_fields
        assert "public_key" in SigningKeyAdmin.readonly_fields
        assert "algorithm" in SigningKeyAdmin.readonly_fields

    def test_has_add_permission__denied(self, rf):
        model_admin = admin.site._registry[SigningKey]
        assert model_admin.has_add_permission(rf.get("/admin/")) is False
