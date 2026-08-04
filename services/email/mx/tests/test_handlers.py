from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.core import mail

from domains.models import Domain
from services.email.mx.handlers import process_incoming_message
from services.email.mx.models import IncomingMessage


def make_raw_email(subject="Postmaster alert"):
    msg = EmailMessage()
    msg["From"] = "external@example.org"
    msg["To"] = "postmaster@example.com"
    msg["Subject"] = subject
    msg.set_content("Something happened")
    return msg.as_bytes()


class TestProcessIncomingMessagePostmaster:
    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch.object(type(org), "billing_is_active", True):
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
            )
        assert (
            IncomingMessage.objects.filter(
                org=org, rcpt_to="postmaster@example.com"
            ).count()
            == 1
        )

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster_plus_addressing__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch.object(type(org), "billing_is_active", True):
            await process_incoming_message(
                "external@example.org",
                "postmaster+bounces@example.com",
                make_raw_email(),
                True,
                domain,
            )
        assert (
            IncomingMessage.objects.filter(
                org=org, rcpt_to="postmaster+bounces@example.com"
            ).count()
            == 1
        )

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__enqueues_notification(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch.object(type(org), "billing_is_active", True):
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
            )
        assert any("postmaster" in m.subject.lower() for m in mail.outbox)

    @pytest.mark.django_db(transaction=True)
    async def test_non_postmaster__does_not_notify(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch.object(type(org), "billing_is_active", True):
            await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                True,
                domain,
            )
        assert len(mail.outbox) == 0
