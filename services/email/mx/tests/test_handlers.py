from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail

from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mx.handlers import MXHandler, process_incoming_message
from services.email.mx.models import IncomingMessage, TlsReport


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
        result = await process_incoming_message(
            "external@example.org",
            "postmaster@example.com",
            make_raw_email(),
            True,
            domain,
        )
        message = await IncomingMessage.objects.aget(
            org=org,
            rcpt_to="postmaster@example.com",
        )
        assert result == "250 OK"
        assert message.domain == domain

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster_plus_addressing__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
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
        org.billing_is_active = True
        result = await process_incoming_message(
            "external@example.org",
            "info@example.com",
            make_raw_email(),
            True,
            domain,
        )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.org == org
        assert len(mail.outbox) == 0


class TestHandleRcpt:
    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__rejects_unknown_domain(self, org):
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@unknown.example",
            None,
        )

        assert result == "550 Relay not authorised for this recipient"
        assert envelope.rcpt_tos == []

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__accepts_managed_domain(self, org):
        domain = await Domain.objects.aget(org=org, is_managed=True)
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            f"user@{domain.name}",
            None,
        )

        assert result == "250 OK"
        assert envelope.recipient_domain == domain

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__selects_most_specific_domain(self, org):
        Domain.objects.create(name="example.com", org=org)
        child = Domain.objects.create(name="app.example.com", org=org)
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@app.example.com",
            None,
        )

        assert result == "250 OK"
        assert envelope.recipient_domain == child

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__rejects_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
    ):
        await Domain.objects.abulk_create(
            [
                Domain(name="example.com", org=org),
                Domain(name="app.example.com", org=write_org),
            ]
        )
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@app.example.com",
            None,
        )

        assert result == "550 Relay not authorised for this recipient"
        assert envelope.rcpt_tos == []
        assert not hasattr(envelope, "recipient_domain")


class TestProcessIncomingMessageBilling:
    @pytest.mark.django_db(transaction=True)
    async def test_unbilled_org__rejects_external_sender(self, org):
        org.billing_is_active = False
        domain = Domain.objects.create(name="example.com", org=org)

        result = await process_incoming_message(
            "external@example.org",
            "info@example.com",
            make_raw_email(),
            True,
            domain,
        )

        assert result == "550 Sender not allowed without active billing"
        assert not await IncomingMessage.objects.filter(domain=domain).aexists()

    @pytest.mark.django_db(transaction=True)
    async def test_unbilled_org__accepts_member_sender_case_insensitively(
        self,
        org,
        user,
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        result = await process_incoming_message(
            user.email.upper(),
            "info@example.com",
            make_raw_email(),
            True,
            domain,
        )

        assert result == "250 OK"
        assert await IncomingMessage.objects.filter(domain=domain).aexists()

    @pytest.mark.django_db(transaction=True)
    async def test_unbilled_org__accepts_plus_addressed_bounce(self, org):
        domain = Domain.objects.create(name="example.com", org=org)

        with patch(
            "services.email.mx.handlers.notify_postmaster_recipients"
        ) as notify_task:
            result = await process_incoming_message(
                "external@example.org",
                "bounce+message-id@example.com",
                make_raw_email(),
                True,
                domain,
            )

        assert result == "250 OK"
        assert await IncomingMessage.objects.filter(domain=domain).aexists()
        notify_task.enqueue.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    async def test_unbilled_org__does_not_exempt_bare_bounce(self, org):
        org.billing_is_active = False
        domain = Domain.objects.create(name="example.com", org=org)

        result = await process_incoming_message(
            "external@example.org",
            "bounce@example.com",
            make_raw_email(),
            True,
            domain,
        )

        assert result == "550 Sender not allowed without active billing"
        assert not await IncomingMessage.objects.filter(domain=domain).aexists()


class TestProcessIncomingMessageReports:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize(
        ("local_part", "report_model"),
        [
            (settings.RELAY_DMARC_REPORT_LOCAL_PART, DmarcReport),
            (settings.RELAY_TLS_REPORT_LOCAL_PART, TlsReport),
            (settings.RELAY_DMARC_RUF_LOCAL_PART, DmarcFailureReport),
        ],
    )
    async def test_report_recipient__binds_report_to_domain(
        self,
        org,
        local_part,
        report_model,
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        with (
            patch("services.email.dmarc.tasks.parse_dmarc_report"),
            patch("services.email.mx.handlers.parse_tls_report"),
            patch("services.email.dmarc.tasks.parse_dmarc_failure_report"),
        ):
            result = await process_incoming_message(
                "external@example.org",
                f"{local_part}@example.com",
                make_raw_email(),
                True,
                domain,
            )

        report = await report_model.objects.aget(domain=domain)
        assert result == "250 OK"
        assert report.org == org
