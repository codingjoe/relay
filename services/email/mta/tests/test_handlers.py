from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail

from abstract.mailauth import Disposition
from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mta.handlers import MXHandler, process_incoming_message
from services.email.mta.models import IncomingMessage, TlsReport
from services.email.mta.tests.conftest import make_dmarc_evaluation, make_raw_email
from services.email.reputation.models import FblReport


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
    async def test_handle_rcpt__keeps_recipient_domain_for_multiple_recipients(
        self,
        org,
    ):
        domain = await Domain.objects.aget(org=org, is_managed=True)
        envelope = SimpleNamespace(rcpt_tos=[])
        handler = MXHandler()

        first = await handler.handle_RCPT(
            None,
            None,
            envelope,
            f"alice@{domain.name}",
            None,
        )
        second = await handler.handle_RCPT(
            None,
            None,
            envelope,
            f"bob@{domain.name}",
            None,
        )

        assert first == "250 OK"
        assert second == "250 OK"
        assert envelope.recipient_domain == domain
        assert envelope.rcpt_tos == [f"alice@{domain.name}", f"bob@{domain.name}"]

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


class TestMXHandler:
    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__rejects_on_dmarc_reject(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="external@example.org",
            rcpt_tos=["info@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.REJECT),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "550 Message rejected by DMARC policy"
        assert not await IncomingMessage.objects.aexists()
        spam_task.enqueue.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__quarantines_on_dmarc_quarantine(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="external@example.org",
            rcpt_tos=["info@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.QUARANTINE),
            ),
            patch("services.email.mta.handlers.check_incoming_spam"),
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.status == IncomingMessage.Status.QUARANTINED

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__accepts_on_dmarc_none(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="external@example.org",
            rcpt_tos=["info@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.NONE),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.status == IncomingMessage.Status.RECEIVED
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip="127.0.0.1"
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_recipient_from_listed_sender_creates_report(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDERS = ["feedback@gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="feedback@gmail.com",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.NONE),
            ),
            patch(
                "services.email.reputation.signals.tasks.create_provider_fbl_report"
            ) as report_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        report_task.enqueue.assert_called_once_with(
            message_pk=str((await IncomingMessage.objects.aget()).id)
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_recipient_unknown_sender_checks_spam(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDERS = ["feedback@gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="forged@example.org",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.NONE),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        spam_task.enqueue.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_on_customer_domain_checks_spam(self, org, settings):
        settings.RELAY_FBL_ADDRESS = "fbl@relays.test"
        settings.RELAY_FBL_SENDERS = ["feedback@gmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="feedback@gmail.com",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.NONE),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        assert not await FblReport.objects.aexists()
        spam_task.enqueue.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__seals_accepted_message_with_arc(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="external@example.org",
            rcpt_tos=["info@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(Disposition.NONE),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert b"ARC-Authentication-Results" in message.raw_body.read()
        spam_task.enqueue.assert_called_once()
