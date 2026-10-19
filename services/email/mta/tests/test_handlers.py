import logging
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from aiosmtpd.smtp import TLSSetupException
from django.conf import settings
from django.core import mail

from abstract.mailauth import Alignment, AuthResult, Disposition
from domains.models import Domain
from services.email.message.models import Transmission
from services.email.mta.handlers import (
    MXHandler,
    is_fbl_report,
    process_incoming_message,
    received_header,
    resolve_remote_host,
)
from services.email.mta.models import IncomingMessage, TlsReport
from services.email.mta.tests.conftest import (
    make_dmarc_evaluation,
    make_dsn_email,
    make_raw_email,
)


class TestProcessIncomingMessagePostmaster:
    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
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
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )
        assert (
            IncomingMessage.objects.filter(
                org=org, rcpt_to="postmaster+bounces@example.com"
            ).count()
            == 1
        )

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__enqueues_only_spam_check(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam") as spam_task:
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip=""
        )
        assert len(mail.outbox) == 0

    @pytest.mark.django_db(transaction=True)
    async def test_non_postmaster__does_not_send_mail(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        org.billing_is_active = True
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
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
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.QUARANTINED,
                make_dmarc_evaluation(),
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.status == IncomingMessage.Status.QUARANTINED

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__message_creation_failure__does_not_mask_integrity_error(
        self, org
    ):
        """A storage failure propagates instead of an IntegrityError."""
        domain = Domain.objects.create(name="example.com", org=org)
        with (
            patch(
                "services.email.mta.models.IncomingMessage.objects.create",
                side_effect=RuntimeError("storage unavailable"),
            ),
            pytest.raises(RuntimeError, match="storage unavailable"),
        ):
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )
        assert await Transmission.objects.acount() == 0


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
    async def test_report_recipient__binds_report_to_domain(self, org):
        domain = Domain.objects.create(name="example.com", org=org)

        with patch("services.email.mta.handlers.parse_tls_report"):
            result = await process_incoming_message(
                "external@example.org",
                f"{settings.RELAY_TLS_REPORT_LOCAL_PART}@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )

        report = await TlsReport.objects.aget(domain=domain)
        assert result == "250 OK"
        assert report.org == org


class TestResolveRemoteHost:
    def test_resolve_remote_host__returns_ptr_hostname(self, dns_resolver):
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "dns.google.")
        assert resolve_remote_host("8.8.8.8") == "dns.google"

    def test_resolve_remote_host__returns_empty_string_without_ptr(self, dns_resolver):
        assert resolve_remote_host("8.8.8.8") == ""

    def test_resolve_remote_host__skips_private_addresses(self, dns_resolver):
        assert resolve_remote_host("10.244.0.1") == ""
        assert dns_resolver.lookups == []

    def test_resolve_remote_host__skips_malformed_addresses(self, dns_resolver):
        assert resolve_remote_host("not-an-ip") == ""
        assert dns_resolver.lookups == []


class TestProcessIncomingMessageTransmission:
    @pytest.mark.django_db(transaction=True)
    async def test_reception__stores_addresses_and_remote_host(self, org, dns_resolver):
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "dns.google.")
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "8.8.8.8",
                "188.245.198.157",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        transmission = await Transmission.objects.aget(message_id=message.pk)
        assert transmission.local_ip_address == "188.245.198.157"
        assert transmission.remote_ip_address == "8.8.8.8"
        assert transmission.remote_host == "dns.google"


class TestProcessIncomingMessageBounces:
    @pytest.mark.django_db(transaction=True)
    async def test_bounce_dsn__stores_message_and_enqueues_parse_task(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        token = uuid4()
        with (
            patch("services.email.msa.signals.tasks.parse_bounce_report") as parse_task,
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await process_incoming_message(
                "mailer-daemon@mx.remote.example",
                f"bounce+{token}@{domain.sender_domain}",
                make_dsn_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.org == org
        assert message.rcpt_to == f"bounce+{token}@{domain.sender_domain}"
        assert message.status == IncomingMessage.Status.RECEIVED
        parse_task.enqueue.assert_called_once_with(message_pk=str(message.id))
        spam_task.enqueue.assert_not_called()
        assert len(mail.outbox) == 0

    @pytest.mark.django_db(transaction=True)
    async def test_bounce_address__non_dsn_mail_runs_spam_check(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        token = uuid4()
        with (
            patch("services.email.msa.signals.tasks.parse_bounce_report") as parse_task,
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await process_incoming_message(
                "external@example.org",
                f"bounce+{token}@{domain.sender_domain}",
                make_raw_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip=""
        )
        parse_task.enqueue.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    async def test_dsn_mail__non_bounce_recipient_runs_spam_check(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with (
            patch("services.email.msa.signals.tasks.parse_bounce_report") as parse_task,
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await process_incoming_message(
                "mailer-daemon@mx.remote.example",
                "info@example.com",
                make_dsn_email(),
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(),
                "",
            )

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.rcpt_to == "info@example.com"
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip=""
        )
        parse_task.enqueue.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    async def test_bounce_address__feedback_report_runs_spam_check(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        token = uuid4()
        report = (
            "From: feedback@gmail.com\r\n"
            f"To: bounce+{token}@{domain.sender_domain}\r\n"
            "Subject: FBL Report\r\n"
            "MIME-Version: 1.0\r\n"
            "Content-Type: multipart/report; report-type=feedback-report;\r\n"
            ' boundary="=_relay-arf-boundary"\r\n'
            "\r\n"
            "--=_relay-arf-boundary\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "This is an authentication failure report.\r\n"
            "--=_relay-arf-boundary\r\n"
            "Content-Type: message/feedback-report\r\n"
            "\r\n"
            "Feedback-Type: abuse\r\n"
            "User-Agent: Gmail/FBL\r\n"
            "Version: 1.0\r\n"
            "--=_relay-arf-boundary--\r\n"
        ).encode()
        with (
            patch("services.email.msa.signals.tasks.parse_bounce_report") as parse_task,
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await process_incoming_message(
                "feedback@gmail.com",
                f"bounce+{token}@{domain.sender_domain}",
                report,
                {"ssl_object": None},
                domain,
                IncomingMessage.Status.RECEIVED,
                make_dmarc_evaluation(header_from="gmail.com"),
                "",
            )

        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip=""
        )
        parse_task.enqueue.assert_not_called()


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
    async def test_handle_data__rejects_spoofed_sender_failing_spf_and_dkim(
        self, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add("victim.com", "TXT", '"v=spf1 ip4:192.0.2.1 -all"')
        dns_resolver.add("_dmarc.victim.com", "TXT", '"v=DMARC1; p=reject"')
        envelope = SimpleNamespace(
            mail_from="ceo@victim.com",
            rcpt_tos=["postmaster@example.com"],
            content=(
                b"Received: from mx.victim.com (mx.victim.com [192.0.2.1])\r\n"
                b"From: ceo@victim.com\r\n"
                b"To: postmaster@example.com\r\n"
                b"Subject: Test\r\n"
                b"\r\n"
                b"Something happened\r\n"
            ),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("198.51.100.99", 1234), ssl=False)

        result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "550 Message rejected by DMARC policy"
        assert not await IncomingMessage.objects.aexists()

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
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="feedback@arf.mail.yahoo.com",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(
                    Disposition.NONE, header_from="arf.mail.yahoo.com"
                ),
            ),
            patch(
                "services.email.reputation.signals.tasks.create_provider_fbl_report"
            ) as report_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        report_task.enqueue.assert_called_once_with(
            message_pk=str((await IncomingMessage.objects.aget()).id)
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_sender_unauthenticated_checks_spam(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDER_DOMAINS = ["hotmail.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="staff@hotmail.com",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("198.51.100.7", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(
                    Disposition.NONE,
                    header_from="hotmail.com",
                    dkim_result=AuthResult.FAIL,
                    dkim_alignment=Alignment.FAIL,
                    spf_result=AuthResult.FAIL,
                    spf_alignment=Alignment.FAIL,
                ),
            ),
            patch("services.email.mta.handlers.check_incoming_spam") as spam_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        spam_task.enqueue.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_sender_sub_domain_creates_report(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="scomp-feedback@eu.arf.mail.yahoo.com",
            rcpt_tos=["fbl@example.com"],
            content=make_raw_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with (
            patch(
                "abstract.mailauth.DmarcEvaluation.from_bytes",
                return_value=make_dmarc_evaluation(
                    Disposition.NONE, header_from="eu.arf.mail.yahoo.com"
                ),
            ),
            patch(
                "services.email.reputation.signals.tasks.create_provider_fbl_report"
            ) as report_task,
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        report_task.enqueue.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_recipient_unknown_sender_checks_spam(
        self, org, settings
    ):
        settings.RELAY_FBL_ADDRESS = "fbl@example.com"
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
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
        spam_task.enqueue.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__fbl_on_customer_domain_checks_spam(self, org, settings):
        settings.RELAY_FBL_ADDRESS = "fbl@relays.test"
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]
        domain = Domain.objects.create(name="example.com", org=org)
        envelope = SimpleNamespace(
            mail_from="feedback@arf.mail.yahoo.com",
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

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__stamps_received_header_on_accepted_message(self, org):
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
            patch("services.email.mta.handlers.check_incoming_spam"),
        ):
            await MXHandler().handle_DATA(None, session, envelope)

        raw = (await IncomingMessage.objects.aget(domain=domain)).raw_body.read()
        received = raw.index(b"Received: from unknown ([127.0.0.1])")
        original = raw.index(b"From: external@example.org")
        assert received < original


class TestReceivedHeader:
    def test_received_header__helo_ip_and_tls(self):
        session = SimpleNamespace(
            peer=("198.51.100.7", 25),
            ssl={"ssl_object": None},
            host_name="mx.sender.example",
        )

        received = received_header(session).decode()

        assert received.startswith("Received: from mx.sender.example ([198.51.100.7])")
        assert f"by {settings.RELAY_DNS_MX_HOSTNAMES[0]} with ESMTPS;" in received
        assert received.endswith("GMT")

    def test_received_header__unknown_helo_without_tls(self):
        session = SimpleNamespace(peer=("127.0.0.1", 25), ssl=False)

        received = received_header(session).decode()

        assert received.startswith("Received: from unknown ([127.0.0.1])")
        assert "with ESMTP;" in received

    def test_received_header__strips_unsafe_helo_chars(self):
        session = SimpleNamespace(
            peer=("198.51.100.7", 25),
            ssl=False,
            host_name="mail.example\r\nBcc: victim@example.com",
        )

        received = received_header(session).decode()

        assert received.splitlines()[0] == (
            "Received: from mail.exampleBcc:victimexample.com ([198.51.100.7])"
        )
        assert received.count("\r\n") == 2

    def test_received_header__omits_missing_ip(self):
        session = SimpleNamespace(peer=None, ssl=False, host_name="mx.example")

        received = received_header(session).decode()

        assert received.startswith("Received: from mx.example\r\n")
        assert "([127.0.0.1])" not in received


class TestIsFblReport:
    def test_is_fbl_report__listed_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]

        assert is_fbl_report(make_dmarc_evaluation(header_from="arf.mail.yahoo.com"))

    def test_is_fbl_report__sub_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["hotmail.com"]

        assert is_fbl_report(make_dmarc_evaluation(header_from="mail.hotmail.com"))

    def test_is_fbl_report__normalizes_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]

        assert is_fbl_report(
            make_dmarc_evaluation(header_from="ARF.MAIL.YAHOO.COM."),
        )

    def test_is_fbl_report__look_alike_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]

        assert not is_fbl_report(
            make_dmarc_evaluation(header_from="arf.mail.yahoo.com.evil.test"),
        )
        assert not is_fbl_report(
            make_dmarc_evaluation(header_from="evil-arf.mail.yahoo.com"),
        )

    def test_is_fbl_report__unlisted_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]

        assert not is_fbl_report(make_dmarc_evaluation(header_from="example.org"))

    def test_is_fbl_report__missing_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["arf.mail.yahoo.com"]

        assert not is_fbl_report(make_dmarc_evaluation(header_from=""))
        assert not is_fbl_report(make_dmarc_evaluation(header_from=None))

    def test_is_fbl_report__no_listed_domain(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = []

        assert not is_fbl_report(
            make_dmarc_evaluation(header_from="arf.mail.yahoo.com")
        )

    def test_is_fbl_report__unauthenticated_claimed_provider(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["hotmail.com"]

        assert not is_fbl_report(
            make_dmarc_evaluation(
                header_from="hotmail.com",
                dkim_result=AuthResult.FAIL,
                dkim_alignment=Alignment.FAIL,
                spf_result=AuthResult.FAIL,
                spf_alignment=Alignment.FAIL,
            )
        )

    def test_is_fbl_report__spf_only_authentication(self, settings):
        settings.RELAY_FBL_SENDER_DOMAINS = ["hotmail.com"]

        assert is_fbl_report(
            make_dmarc_evaluation(
                header_from="hotmail.com",
                dkim_result=AuthResult.FAIL,
                dkim_alignment=Alignment.FAIL,
            )
        )


class TestHandleException:
    async def test__tls_setup_exception_muted(self, caplog):
        caplog.set_level(logging.DEBUG, logger="services.email.mta.handlers")
        result = await MXHandler().handle_exception(TLSSetupException())

        assert result == "500 Error: (TLSSetupException) "
        records = [r for r in caplog.records if r.name == "services.email.mta.handlers"]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG

    async def test__other_exception_logged(self, caplog):
        caplog.set_level(logging.WARNING, logger="services.email.mta.handlers")
        result = await MXHandler().handle_exception(ValueError("boom"))

        assert result == "500 Error: (ValueError) boom"
        records = [r for r in caplog.records if r.name == "services.email.mta.handlers"]
        assert len(records) == 1
        assert records[0].levelno == logging.ERROR
