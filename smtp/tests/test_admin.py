from django.contrib import admin

from smtp.admin import OutgoingMessageAdmin, SmtpCredentialAdmin, TransmissionAdmin
from smtp.models import OutgoingMessage, SmtpCredential, Transmission


class TestOutgoingMessageAdmin:
    def test_outgoing_message_admin__registered(self):
        assert isinstance(admin.site._registry[OutgoingMessage], OutgoingMessageAdmin)

    def test_outgoing_message_admin__search_fields(self):
        assert "mail_from" in OutgoingMessageAdmin.search_fields
        assert "rcpt_to" in OutgoingMessageAdmin.search_fields


class TestTransmissionAdmin:
    def test_transmission_admin__registered(self):
        assert isinstance(admin.site._registry[Transmission], TransmissionAdmin)


class TestSmtpCredentialAdmin:
    def test_smtp_credential_admin__registered(self):
        assert isinstance(admin.site._registry[SmtpCredential], SmtpCredentialAdmin)

    def test_smtp_credential_admin__readonly_key_hash(self):
        assert "key_hash" in SmtpCredentialAdmin.readonly_fields
        assert "key_prefix" in SmtpCredentialAdmin.readonly_fields
