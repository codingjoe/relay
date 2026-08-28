from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail

from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mta.handlers import MXHandler, process_incoming_message
from services.email.mta.models import IncomingMessage, TlsReport
from services.email.reputation.models import FblReport


def make_raw_email(subject="Postmaster alert"):
    msg = EmailMessage()
    msg["From"] = "external@example.org"
    msg["To"] = "postmaster@example.com"
    msg["Subject"] = subject
    msg.set_content("Something happened")
    return msg.as_bytes()


def make_fbl_report_email():
    msg = EmailMessage()
    msg["From"] = "feedback@gmail.com"
    msg["To"] = "fbl@example.com"
    msg["Subject"] = "Complaint report"
    msg.set_content("Abuse report")
    msg.add_attachment(
        b"Feedback-Type: fraud\n"
        b"Source-IP: 192.0.2.1\n"
        b"Original-Mail-From: spammer@acme.com\n",
        maintype="message",
        subtype="feedback-report",
    )
    return msg.as_bytes()


class TestProcessIncomingMessagePostmaster:
    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
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
        with patch("services.email.mta.handlers.check_incoming_spam"):
            await process_incoming_message(
                "external@example.org",
                "postmaster+bounces@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
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
        with patch("services.email.mta.handlers.check_incoming_spam"):
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        assert any("postmaster" in m.subject.lower() for m in mail.outbox)

    @pytest.mark.django_db(transaction=True)
    async def test_non_postmaster__does_not_notify(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        org.billing_is_active = True
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.org == org
        assert len(mail.outbox) == 0

    @pytest.mark.django_db(transaction=True)
    async def test_quarantined_status__stored_with_quarantine(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.QUARANTINED,
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.status == IncomingMessage.Status.QUARANTINED


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
            patch("services.email.mta.handlers.parse_tls_report"),
            patch("services.email.dmarc.tasks.parse_dmarc_failure_report"),
        ):
            result = await process_incoming_message(
                "external@example.org",
                f"{local_part}@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        report = await report_model.objects.aget(domain=domain)
        assert result == "250 OK"
        assert report.org == org


class TestProcessIncomingMessageFbl:
    @pytest.mark.django_db(transaction=True)
    async def test_fbl__creates_fbl_report_and_parses_it(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        result = await process_incoming_message(
            "feedback@gmail.com",
            f"{settings.RELAY_FBL_LOCAL_PART}@example.com",
            make_fbl_report_email(),
            True,
            domain,
            IncomingMessage.Status.RECEIVED,
            "",
        )

        assert result == "250 OK"
        report = await FblReport.objects.aget(org=org)
        assert report.mail_from == "feedback@gmail.com"
        assert report.domain == domain
        assert report.receiving_domain == "example.com"
        assert report.received_with_tls is True
        assert report.feedback_type == "fraud"
        assert report.original_mail_from == "spammer@acme.com"
