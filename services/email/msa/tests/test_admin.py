import pytest
from django.contrib import admin, messages
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from domains.models import Domain
from services.email.message.admin import TransmissionAdmin
from services.email.message.models import Transmission
from services.email.msa.admin import (
    MsaCredentialAdmin,
    OutgoingMessageAdmin,
)
from services.email.msa.models import MsaCredential, OutgoingMessage
from services.email.spam.client import VirusAction


def make_request():
    request = RequestFactory().post("/admin/")
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def make_message(org, **kwargs):
    return OutgoingMessage.objects.create(
        org=org,
        domain=Domain.objects.get(org=org, is_managed=True),
        rcpt_to="bob@example.com",
        mail_from="alice@example.com",
        **kwargs,
    )


class TestOutgoingMessageAdmin:
    def test_outgoing_message_admin__registered(self):
        assert isinstance(admin.site._registry[OutgoingMessage], OutgoingMessageAdmin)

    def test_outgoing_message_admin__search_fields(self):
        assert "mail_from" in OutgoingMessageAdmin.search_fields
        assert "rcpt_to" in OutgoingMessageAdmin.search_fields


class TestReleaseSpamHoldsPermissions:
    def test_release_spam_holds__requires_change_permission(self):
        assert OutgoingMessageAdmin.release_spam_holds.allowed_permissions == ["change"]


@pytest.mark.django_db
class TestReleaseSpamHoldsAction:
    def test_release_spam_holds__releases_selected_clean_holds(self, org):
        first = make_message(
            org,
            status=OutgoingMessage.Status.HELD,
            virus_action=VirusAction.CLEAN,
        )
        second = make_message(
            org,
            status=OutgoingMessage.Status.HELD,
            virus_action=VirusAction.CLEAN,
        )
        model_admin = OutgoingMessageAdmin(OutgoingMessage, admin.site)
        request = make_request()

        model_admin.release_spam_holds(
            request,
            OutgoingMessage.objects.filter(pk__in=[first.pk, second.pk]),
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == OutgoingMessage.Status.PENDING
        assert second.status == OutgoingMessage.Status.PENDING
        stored = list(get_messages(request))
        assert [str(message) for message in stored] == ["Released 2 messages."]
        assert stored[0].level == messages.SUCCESS

    def test_release_spam_holds__warns_when_nothing_is_releasable(self, org):
        msg = make_message(
            org,
            status=OutgoingMessage.Status.HELD,
            virus_action=VirusAction.INFECTED,
        )
        model_admin = OutgoingMessageAdmin(OutgoingMessage, admin.site)
        request = make_request()

        model_admin.release_spam_holds(
            request,
            OutgoingMessage.objects.filter(pk=msg.pk),
        )

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.HELD
        stored = list(get_messages(request))
        assert [str(message) for message in stored] == [
            "No selected message was a held spam message."
        ]
        assert stored[0].level == messages.WARNING


class TestTransmissionAdmin:
    def test_transmission_admin__registered(self):
        assert isinstance(
            admin.site._registry[Transmission],
            TransmissionAdmin,
        )


class TestMsaCredentialAdmin:
    def test_smtp_credential_admin__registered(self):
        assert isinstance(admin.site._registry[MsaCredential], MsaCredentialAdmin)

    def test_smtp_credential_admin__readonly_key_hash(self):
        assert "key_hash" in MsaCredentialAdmin.readonly_fields
        assert "key_prefix" in MsaCredentialAdmin.readonly_fields
