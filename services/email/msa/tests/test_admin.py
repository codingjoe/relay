from django.contrib import admin

from services.email.msa.admin import (
    MsaCredentialAdmin,
    OutgoingMessageAdmin,
    TransmissionAdmin,
)
from services.email.msa.models import MsaCredential, OutgoingMessage, Transmission


class TestOutgoingMessageAdmin:
    def test_outgoing_message_admin__registered(self):
        assert isinstance(admin.site._registry[OutgoingMessage], OutgoingMessageAdmin)

    def test_outgoing_message_admin__search_fields(self):
        assert "mail_from" in OutgoingMessageAdmin.search_fields
        assert "rcpt_to" in OutgoingMessageAdmin.search_fields


class TestTransmissionAdmin:
    def test_transmission_admin__registered(self):
        assert isinstance(admin.site._registry[Transmission], TransmissionAdmin)


class TestMsaCredentialAdmin:
    def test_smtp_credential_admin__registered(self):
        assert isinstance(admin.site._registry[MsaCredential], MsaCredentialAdmin)

    def test_smtp_credential_admin__readonly_key_hash(self):
        assert "key_hash" in MsaCredentialAdmin.readonly_fields
        assert "key_prefix" in MsaCredentialAdmin.readonly_fields
