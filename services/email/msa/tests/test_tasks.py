import base64
import datetime
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import dns.exception
import pytest
from botocore.exceptions import ClientError
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from abstract.mailauth import Disposition
from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.models import (
    MsaCredential,
    OutgoingMessage,
    SuppressionEntry,
)
from services.email.msa.tasks import (
    DELIVERY_RETRY,
    DeliveryStatus,
    DsnAction,
    MxLookupError,
    TemporaryDeliveryError,
    bounce_signer,
    check_outgoing_spam,
    deliver_message,
    delivery_retry,
    fetch_mx_hosts,
    mint_bounce_address,
    parse_bounce_report,
    parse_delivery_status,
    resolve_bounce_owner,
)
from services.email.mta.handlers import MXHandler
from services.email.mta.models import IncomingMessage
from services.email.mta.tests.conftest import (
    make_delayed_dsn_email,
    make_dmarc_evaluation,
    make_dsn_email,
    make_raw_email,
)
from services.email.spam.client import SpamAction, SpamResult


def make_certificate(common_name):
    """Return a self-signed TLS certificate for the given DNS name."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )


def make_outgoing_message(org, domain=None, status=OutgoingMessage.Status.PENDING):
    """Return a stored outgoing message without a deliverable sender."""
    if domain is None:
        domain = Domain.objects.get(org=org)
    msg = OutgoingMessage.objects.create(
        org=org,
        rcpt_to="bob@example.net",
        mail_from="alice@example.com",
        domain=domain,
        status=status,
    )
    msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
    msg.save(update_fields=["raw_body"])
    return msg


def make_bounce_dsn(org, domain, rcpt_to, raw_bytes):
    """Store an incoming bounce DSN the way the MTA handler stores it."""
    message = IncomingMessage.objects.create(
        org=org,
        domain=domain,
        receiving_domain=domain.name,
        mail_from="mailer-daemon@mx.remote.example",
        rcpt_to=rcpt_to,
        subject="Undelivered Mail Returned to Sender",
        message_id="<dsn-1@mx.remote.example>",
        headers=[],
    )
    message.raw_body.save("bounce.eml", ContentFile(raw_bytes), save=False)
    message.save(update_fields=["raw_body"])
    return message


class TestMintBounceAddress:
    def test_mint_bounce_address__local_part_within_rfc_limit(self):
        message = SimpleNamespace(
            pk=uuid.uuid4(), domain=SimpleNamespace(sender_domain="example.com")
        )

        local_part = mint_bounce_address(message).partition("@")[0]

        assert len(local_part.encode()) <= 64


class TestFetchMxHosts:
    def test_fetch_mx_hosts__sorted_by_priority(self, dns_resolver):
        dns_resolver.add(
            "example.com", "MX", "20 mx2.example.com.", "10 mx1.example.com."
        )
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx1.example.com", "mx2.example.com"]

    def test_fetch_mx_hosts__strips_trailing_dot(self, dns_resolver):
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx.example.com"]

    def test_fetch_mx_hosts__empty_when_domain_is_unknown(self):
        assert fetch_mx_hosts("nonexistent.invalid") == []

    def test_fetch_mx_hosts__raises_lookup_error_when_the_resolver_fails(
        self, dns_resolver
    ):
        dns_resolver.fail("example.com", "MX", dns.exception.Timeout())
        with pytest.raises(MxLookupError, match="MX lookup for example.com failed"):
            fetch_mx_hosts("example.com")


@pytest.mark.django_db(transaction=True)
class TestDeliverMessage:
    def test_deliver_message__no_mx_records(self, user, org, dns_resolver):
        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@nowhere.invalid",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        with pytest.raises(TemporaryDeliveryError, match="No MX"):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert Transmission.objects.filter(message=msg).count() == 1
        t = Transmission.objects.get(message=msg)
        assert t.status == Transmission.Status.FAILED
        assert "No MX" in t.details

    def test_deliver_message__sends_with_bounce_return_path(
        self, user, org, dns_resolver, caplog
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        caplog.set_level(logging.INFO)
        certificate = make_certificate("mx.example.com")
        ssl_object = MagicMock()
        ssl_object.get_unverified_chain.return_value = [
            certificate.public_bytes(Encoding.DER)
        ]
        smtp_client = MagicMock()
        smtp_client.sendmail = AsyncMock(return_value="250 OK")
        smtp_client.__aenter__.return_value = smtp_client
        smtp_client.get_transport_info.side_effect = {
            "ssl_object": ssl_object,
            "cipher": ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 32),
            "sockname": ("198.51.100.25", 40000),
            "peername": ("203.0.113.10", 25),
        }.get
        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            return_value=smtp_client,
        ) as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        assert (
            mock_smtp.call_args.kwargs["local_hostname"]
            == settings.SMTP_PUBLIC_HOSTNAME
        )
        assert mock_smtp.call_args.kwargs["port"] == 25
        assert mock_smtp.call_args.kwargs["use_tls"] is False
        assert mock_smtp.call_args.kwargs["start_tls"] is True
        assert smtp_client.sendmail.call_args.args[0] == mint_bounce_address(msg)
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SENT
        transmission = Transmission.objects.get(
            message=msg, status=Transmission.Status.SENT
        )
        assert transmission.remote_host == "mx.example.com"
        assert transmission.tls_mode == Transmission.TlsMode.STARTTLS
        assert transmission.tls_version == "TLSv1.3"
        assert transmission.tls_cipher == "TLS_AES_256_GCM_SHA384"
        assert transmission.local_ip_address == "198.51.100.25"
        assert transmission.remote_ip_address == "203.0.113.10"
        stored_certificate = transmission.tls_certificate
        assert (
            stored_certificate.fingerprint
            == certificate.fingerprint(hashes.SHA256()).hex()
        )
        assert stored_certificate.subject == "CN=mx.example.com"
        assert stored_certificate.subject_alternative_names == "mx.example.com"
        assert stored_certificate.issuer == "CN=mx.example.com"
        assert stored_certificate.serial_number == format(
            certificate.serial_number, "x"
        )
        assert stored_certificate.not_before == certificate.not_valid_before_utc
        assert stored_certificate.not_after == certificate.not_valid_after_utc
        assert stored_certificate.issuer_certificate is None
        assert list(stored_certificate.chain()) == [stored_certificate]
        assert (
            f"Message {msg!r} delivered via 'mx.example.com' "
            "from 198.51.100.25: '250 OK'" in caplog.messages
        )

    def test_deliver_message__permanent_failure_marks_bounced(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="reject@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        exc = aiosmtplib.SMTPResponseException(550, b"User unknown")
        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            side_effect=exc,
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.BOUNCED
        ).exists()

    def test_deliver_message__failed_dial_records_pool_address(
        self, user, org, dns_resolver, settings, caplog
    ):
        settings.SMTP_SOURCE_IPS = ["198.51.100.7"]

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=OSError("Network is unreachable"),
            ),
            caplog.at_level(logging.INFO),
            pytest.raises(TemporaryDeliveryError, match="Network is unreachable"),
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.local_ip_address == "198.51.100.7"
        assert transmission.remote_ip_address is None
        assert f"Message {msg!r} failed, relay retries" in caplog.messages
        assert "OSError: Network is unreachable" in caplog.text

    def test_deliver_message__bounce_records_pool_address(
        self, user, org, dns_resolver, settings, caplog
    ):
        settings.SMTP_SOURCE_IPS = ["198.51.100.7"]

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="reject@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        refusal = aiosmtplib.SMTPRecipientRefused(
            550, b"5.1.1 User unknown", msg.rcpt_to
        )
        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=aiosmtplib.SMTPRecipientsRefused([refusal]),
            ),
            caplog.at_level(logging.WARNING),
        ):
            deliver_message.func(message_id=str(msg.id))

        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.BOUNCED
        assert transmission.local_ip_address == "198.51.100.7"
        assert (
            f"Message {msg!r} bounced at 'mx.example.com' "
            "from 198.51.100.7: '550 5.1.1 User unknown'" in caplog.messages
        )

    def test_deliver_message__dials_from_the_pool_address(
        self, user, org, dns_resolver, settings, caplog
    ):
        settings.SMTP_SOURCE_IPS = ["198.51.100.7"]

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        smtp_client = MagicMock()
        smtp_client.sendmail = AsyncMock(return_value="250 OK")
        smtp_client.__aenter__.return_value = smtp_client
        smtp_client.get_transport_info.side_effect = {
            "sockname": ("198.51.100.7", 40000),
            "peername": ("203.0.113.10", 25),
        }.get
        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                return_value=smtp_client,
            ) as mock_smtp,
            caplog.at_level(logging.INFO),
        ):
            deliver_message.func(message_id=str(msg.id))

        assert mock_smtp.call_args.kwargs["source_address"] == ("198.51.100.7", 0)
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.SENT
        assert transmission.local_ip_address == "198.51.100.7"
        assert transmission.remote_ip_address == "203.0.113.10"
        assert (
            f"Message {msg!r} delivered via 'mx.example.com' "
            "from 198.51.100.7: '250 OK'" in caplog.messages
        )

    def test_deliver_message__fails_closed_for_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
        other_user,
    ):

        _, child = Domain.objects.bulk_create(
            [
                Domain(name="example.com", org=org),
                Domain(name="app.example.com", org=write_org),
            ]
        )
        msg = OutgoingMessage.objects.create(
            org=write_org,
            rcpt_to="bob@example.com",
            mail_from=f"alice@{child.name}",
            domain=child,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="ambiguous",
        ).exists()
        mock_smtp.assert_not_called()

    def test_deliver_message__drops_message_of_locked_org(self, user, org):
        domain = Domain.objects.get(org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        message.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        message.save()

        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at", "modified_at"])

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(message.id))

        mock_smtp.assert_not_called()
        message.refresh_from_db()
        assert message.status == OutgoingMessage.Status.DROPPED
        transmission = Transmission.objects.get(message=message)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.code == 550
        assert transmission.output == "550 Account suspended due to sender reputation"

    def test_deliver_message__skips_message_with_final_status(self, user, org):
        message = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=Domain.objects.get(org=org),
            status=OutgoingMessage.Status.SANDBOXED,
        )
        message.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        message.save()

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(message.id))

        mock_smtp.assert_not_called()
        message.refresh_from_db()
        assert message.status == OutgoingMessage.Status.SANDBOXED
        assert not Transmission.objects.filter(message=message).exists()

    def test_deliver_message__records_sandbox_attempt_without_transmitting(
        self, user, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        # The credential that submitted this message is gone, the flag holds.
        msg = self.make_message(user, org, domain, is_sandbox=True)

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SANDBOXED
        transmission = Transmission.objects.get(
            message=msg, status=Transmission.Status.SANDBOXED
        )
        assert transmission.remote_host == "mx.example.com"
        assert transmission.details == (
            "Sandbox submission, relay made no delivery attempt"
        )
        assert not Transmission.objects.filter(
            message=msg, status=Transmission.Status.FAILED
        ).exists()

    def test_deliver_message__records_sandbox_attempt_without_a_host(
        self, user, org, dns_resolver
    ):
        msg = self.make_message(
            user,
            org,
            Domain.objects.create(name="example.com", org=org),
            is_sandbox=True,
        )

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SANDBOXED
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.SANDBOXED
        assert transmission.remote_host == ""
        assert transmission.details == "No MX records found for example.com"

    def test_deliver_message__records_sandbox_attempt_blocked_by_mta_sts(
        self, user, org, dns_resolver
    ):
        msg = self.make_message(
            user,
            org,
            Domain.objects.create(name="example.com", org=org),
            is_sandbox=True,
        )
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        with (
            patch("services.email.msa.tasks.MtaStsPolicy") as mock_policy,
            patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp,
        ):
            mock_policy.get.return_value.allows.return_value = (
                False,
                "STS policy blocked",
            )
            deliver_message.func(message_id=str(msg.id))

        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SANDBOXED
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.SANDBOXED
        assert transmission.remote_host == "mx.example.com"
        assert transmission.details == "STS policy blocked"

    def test_deliver_message__records_sandbox_attempt_at_the_allowed_host(
        self, user, org, dns_resolver
    ):
        msg = self.make_message(
            user,
            org,
            Domain.objects.create(name="example.com", org=org),
            is_sandbox=True,
        )
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )

        with (
            patch("services.email.msa.tasks.MtaStsPolicy") as mock_policy,
            patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp,
        ):
            mock_policy.get.return_value.allows.side_effect = [
                (False, "STS policy blocked"),
                (True, "STS policy allows"),
            ]
            deliver_message.func(message_id=str(msg.id))

        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SANDBOXED
        assert set(
            Transmission.objects.filter(message=msg).values_list(
                "remote_host", "status", "details"
            )
        ) == {
            (
                "mx1.example.com",
                Transmission.Status.SANDBOXED,
                "STS policy blocked",
            ),
            (
                "mx2.example.com",
                Transmission.Status.SANDBOXED,
                "Sandbox submission, relay made no delivery attempt",
            ),
        }

    @staticmethod
    def make_message(user, org, domain, rcpt_to="bob@example.com", is_sandbox=False):
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to=rcpt_to,
            mail_from="alice@example.com",
            domain=domain,
            is_sandbox=is_sandbox,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()
        return msg

    def test_deliver_message__fails_for_non_canonical_sender_domain(self, user, org):
        # bulk_create bypasses save()/clean(), so the stored name stays
        # non-canonical and no longer matches the resolved root domain.
        (domain,) = Domain.objects.bulk_create([Domain(name="Example.com", org=org)])
        msg = self.make_message(user, org, domain)

        with patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="does not match",
        ).exists()

    def test_deliver_message__skips_hosts_blocked_by_mta_sts(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        with (
            patch("services.email.msa.tasks.MtaStsPolicy") as mock_policy,
            patch("services.email.msa.tasks.aiosmtplib.SMTP") as mock_smtp,
        ):
            mock_policy.get.return_value.allows.return_value = (
                False,
                "STS policy blocked",
            )
            deliver_message.func(message_id=str(msg.id))

        mock_policy.get.return_value.allows.assert_called_once_with("mx.example.com")
        mock_smtp.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.remote_host == "mx.example.com"
        assert transmission.details == "STS policy blocked"

    def test_deliver_message__temporary_smtp_error_keeps_message_pending(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        exc = aiosmtplib.SMTPResponseException(450, b"Try again later")
        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=exc,
            ),
            pytest.raises(TemporaryDeliveryError, match="450 Try again later"),
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.remote_host == "mx.example.com"
        assert transmission.code == 450
        assert transmission.output == "450 Try again later"
        assert "Temporary failure" in transmission.details
        assert not SuppressionEntry.objects.filter(org=org).exists()

    def test_deliver_message__exhausts_all_mx_hosts_on_smtp_exception(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=aiosmtplib.SMTPException("nope"),
            ) as mock_smtp,
            pytest.raises(TemporaryDeliveryError, match="SMTPException: nope"),
        ):
            deliver_message.func(message_id=str(msg.id))

        assert mock_smtp.call_count == 2
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert set(
            Transmission.objects.filter(message=msg).values_list(
                "remote_host", "status", "details"
            )
        ) == {
            ("mx1.example.com", Transmission.Status.FAILED, "SMTPException: nope"),
            ("mx2.example.com", Transmission.Status.FAILED, "SMTPException: nope"),
        }

    def test_deliver_message__refused_recipient_bounces_and_suppresses(
        self, user, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )
        refusal = aiosmtplib.SMTPRecipientRefused(
            550, b"5.1.1 User unknown", msg.rcpt_to
        )

        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            side_effect=aiosmtplib.SMTPRecipientsRefused([refusal]),
        ) as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        assert mock_smtp.call_count == 1
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(message=msg).count() == 1
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.BOUNCED
        assert transmission.remote_host == "mx1.example.com"
        assert transmission.code == 550
        assert transmission.output == "550 5.1.1 User unknown"
        assert "suppressed" in transmission.details
        entry = SuppressionEntry.objects.get(org=org, address_hash__email=msg.rcpt_to)
        assert entry.reason == SuppressionEntry.Reason.BOUNCE

    def test_deliver_message__temporary_recipient_refusal_tries_next_host(
        self, user, org, dns_resolver, caplog
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )
        refusal = aiosmtplib.SMTPRecipientRefused(
            451, b"4.2.1 Try again later", msg.rcpt_to
        )

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=aiosmtplib.SMTPRecipientsRefused([refusal]),
            ) as mock_smtp,
            caplog.at_level(logging.INFO),
            pytest.raises(TemporaryDeliveryError),
        ):
            deliver_message.func(message_id=str(msg.id))

        assert [call.kwargs["hostname"] for call in mock_smtp.call_args_list] == [
            "mx1.example.com",
            "mx2.example.com",
        ]
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert set(
            Transmission.objects.filter(message=msg).values_list(
                "remote_host", "status", "code", "output"
            )
        ) == {
            (
                "mx1.example.com",
                Transmission.Status.FAILED,
                451,
                "451 4.2.1 Try again later",
            ),
            (
                "mx2.example.com",
                Transmission.Status.FAILED,
                451,
                "451 4.2.1 Try again later",
            ),
        }
        assert f"Message {msg!r} failed, relay retries" in caplog.messages
        assert "451 4.2.1 Try again later" in caplog.text

    def test_deliver_message__unexpected_refusal_retries(self, user, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        # aiosmtplib refuses any RCPT answer but 250 and 251, so a server
        # answering 354 reaches the generic wording, not the temporary one.
        refusal = aiosmtplib.SMTPRecipientRefused(354, "Start mail input", msg.rcpt_to)

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=aiosmtplib.SMTPRecipientsRefused([refusal]),
            ),
            pytest.raises(TemporaryDeliveryError, match="354 Start mail input"),
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.code == 354
        assert transmission.output == "354 Start mail input"
        assert transmission.details == "The remote server did not accept the message"

    def test_deliver_message__failed_lookup_reports_the_resolver_error(
        self, user, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.fail("example.com", "MX", dns.exception.Timeout())

        with pytest.raises(TemporaryDeliveryError, match="MX lookup for example.com"):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert Transmission.objects.filter(message=msg).count() == 1
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.remote_host == ""
        assert transmission.details.startswith("MX lookup for example.com failed:")
        assert "No MX records" not in transmission.details

    def test_deliver_message__unexpected_error_repeats_on_the_fallback_row(
        self, user, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.SMTP",
                side_effect=ValueError("error parsing asn1 value"),
            ),
            pytest.raises(TemporaryDeliveryError, match="error parsing asn1 value"),
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert set(
            Transmission.objects.filter(message=msg).values_list(
                "remote_host", "status", "details"
            )
        ) == {
            (
                "mx.example.com",
                Transmission.Status.FAILED,
                "ValueError: error parsing asn1 value",
            ),
            ("", Transmission.Status.FAILED, "error parsing asn1 value"),
        }

    def test_deliver_message__storage_error_keeps_message_pending(
        self, user, org, dns_resolver, caplog
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        # The object store answers with botocore's own exception, not an OSError.
        error = ClientError(
            {
                "Error": {"Code": "SlowDown"},
                "ResponseMetadata": {"HTTPStatusCode": 503},
            },
            "GetObject",
        )
        message_id = str(msg.id)

        with (
            patch(
                "django.core.files.storage.FileSystemStorage.open",
                side_effect=error,
            ),
            caplog.at_level(logging.WARNING),
            pytest.raises(TemporaryDeliveryError, match="SlowDown"),
        ):
            deliver_message.func(message_id=message_id)

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.details == (
            "An error occurred (SlowDown) when calling the GetObject operation: Unknown"
        )
        assert (
            f"Storage error for message {message_id!r}: ClientError('An error occurred "
            "(SlowDown) when calling the GetObject operation: Unknown')"
        ) in caplog.messages


def make_delivery_retry_context(attempt, message_id, error=TemporaryDeliveryError):
    exception = SimpleNamespace(exception_class=error)
    return SimpleNamespace(
        attempt=attempt,
        task_result=SimpleNamespace(
            kwargs={"message_id": message_id}, errors=[exception]
        ),
    )


class TestDeliveryRetry:
    def test_delivery_retry__doubles_the_delay_up_to_the_last_attempt(self):
        # No attempt here is the last one, so the callback never reads the message.
        no_such_message = "00000000-0000-0000-0000-000000000000"
        delays = [
            delivery_retry(make_delivery_retry_context(attempt, no_such_message))
            for attempt in range(1, DELIVERY_RETRY.max_retries)
        ]
        assert delays == [
            datetime.timedelta(minutes=wait_minutes)
            for wait_minutes in (2, 4, 8, 16, 32)
        ]

    @pytest.mark.django_db(transaction=True)
    def test_delivery_retry__stops_retrying_an_unexpected_error(self, org):
        message = make_outgoing_message(org)
        context = make_delivery_retry_context(
            attempt=1, message_id=str(message.pk), error=ValueError
        )

        assert delivery_retry(context) is None

    @pytest.mark.django_db(transaction=True)
    def test_delivery_retry__fails_the_message_of_the_last_attempt(self, org):
        message = make_outgoing_message(org)
        context = make_delivery_retry_context(
            attempt=DELIVERY_RETRY.max_retries, message_id=str(message.pk)
        )

        assert delivery_retry(context) is None

        message.refresh_from_db()
        assert message.status == OutgoingMessage.Status.FAILED

    @pytest.mark.django_db(transaction=True)
    def test_delivery_retry__keeps_a_delivered_message_sent(self, org):
        message = make_outgoing_message(org, status=OutgoingMessage.Status.SENT)
        context = make_delivery_retry_context(
            attempt=DELIVERY_RETRY.max_retries, message_id=str(message.pk)
        )

        delivery_retry(context)

        message.refresh_from_db()
        assert message.status == OutgoingMessage.Status.SENT

    @pytest.mark.django_db(transaction=True)
    def test_delivery_retry__bumps_the_modified_at_of_the_failed_message(self, org):
        message = make_outgoing_message(org)
        modified_at = message.modified_at
        context = make_delivery_retry_context(
            attempt=DELIVERY_RETRY.max_retries, message_id=str(message.pk)
        )

        delivery_retry(context)

        message.refresh_from_db()
        assert message.modified_at > modified_at


@pytest.mark.django_db(transaction=True)
class TestCheckOutgoingSpam:
    def test_check_outgoing_spam__drops_queued_messages_of_suspended_org(
        self, user, org
    ):

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at", "modified_at"])

        check_outgoing_spam.func(message_pk=str(msg.id), client_ip="")

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.DROPPED
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.FAILED
        assert transmission.code == 550
        assert transmission.output == "550 Account suspended due to sender reputation"

    def test_check_outgoing_spam__holds_spam(self, user, org):
        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com, carol@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"spam body"), save=False)
        msg.save()

        with (
            patch(
                "services.email.msa.tasks.check_message",
                return_value=SpamResult(score=10.0, action=SpamAction.REJECT),
            ) as mock_check,
            patch("services.email.msa.tasks.deliver_message") as mock_deliver,
        ):
            check_outgoing_spam.func(message_pk=str(msg.id), client_ip="1.2.3.4")

        mock_check.assert_awaited_once_with(b"spam body", client_ip="1.2.3.4")
        mock_deliver.enqueue.assert_not_called()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.HELD
        assert msg.spam_score == 10.0
        assert msg.spam_action == SpamAction.REJECT

    def test_check_outgoing_spam__enqueues_delivery_of_sandbox_message(self, user, org):
        domain = Domain.objects.get(org=org)
        credential, _ = MsaCredential.objects.create_with_key(
            org=org, type=MsaCredential.Type.SANDBOX
        )
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
            credential=credential,
            is_sandbox=True,
        )
        msg.raw_body.save("test.eml", ContentFile(b"clean body"), save=False)
        msg.save()

        with (
            patch(
                "services.email.msa.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.msa.tasks.deliver_message") as mock_deliver,
        ):
            check_outgoing_spam.func(message_pk=str(msg.id), client_ip="")

        mock_deliver.enqueue.assert_called_once_with(message_id=str(msg.pk))
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert msg.spam_score == 0.0

    def test_check_outgoing_spam__enqueues_delivery_of_clean_message(self, user, org):
        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"clean body"), save=False)
        msg.save()

        with (
            patch(
                "services.email.msa.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.msa.tasks.deliver_message") as mock_deliver,
        ):
            check_outgoing_spam.func(message_pk=str(msg.id), client_ip="")

        mock_deliver.enqueue.assert_called_once_with(message_id=str(msg.pk))
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.PENDING
        assert msg.spam_score == 0.0
        assert not Transmission.objects.filter(message=msg).exists()


class TestParseDeliveryStatus:
    def test_parse_delivery_status__returns_action_code_and_output(self):
        delivery_status = parse_delivery_status(make_dsn_email())

        assert delivery_status == DeliveryStatus(
            action=DsnAction.FAILED,
            code=550,
            output="smtp; 550 5.1.1 User unknown",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__code_falls_back_to_status_class(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(action="delayed", status="4.4.1", diagnostic_code="")
        )

        assert delivery_status == DeliveryStatus(
            action=DsnAction.DELAYED,
            code=400,
            output="4.4.1",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__code_ignored_for_non_smtp_diagnostic(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(
                status="5.1.1",
                diagnostic_code="dns; 203.0.113.5 unreachable",
            )
        )

        assert delivery_status == DeliveryStatus(
            action=DsnAction.FAILED,
            code=500,
            output="dns; 203.0.113.5 unreachable",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__code_falls_back_for_untyped_diagnostic(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(
                status="5.1.1",
                diagnostic_code="550 5.1.1 User unknown",
            )
        )

        assert delivery_status == DeliveryStatus(
            action=DsnAction.FAILED,
            code=500,
            output="550 5.1.1 User unknown",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__code_is_none_for_malformed_status(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(status="55", diagnostic_code="")
        )

        assert delivery_status == DeliveryStatus(
            action=DsnAction.FAILED,
            code=None,
            output="55",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__raises_without_delivery_status_part(self):
        with pytest.raises(ValueError, match="no message/delivery-status part"):
            parse_delivery_status(make_raw_email())

    def test_parse_delivery_status__raises_without_per_recipient_block(self):
        with pytest.raises(ValueError, match="no per-recipient block"):
            parse_delivery_status(make_dsn_email(with_recipient_block=False))

    def test_parse_delivery_status__parses_eight_bit_headers(self):
        raw_bytes = (
            make_dsn_email()
            .replace(b"Action: failed\r\n", b"Action: failed\xff\r\n")
            .replace(
                b"Diagnostic-Code: smtp; 550 5.1.1 User unknown\r\n",
                b"Diagnostic-Code: smtp; 550 5.1.1 User unknown\xff\r\n",
            )
        )

        # An action outside RFC 3464's vocabulary fails closed with the
        # same ValueError path an unreadable DSN takes.
        with pytest.raises(ValueError, match="is not a valid DsnAction"):
            parse_delivery_status(raw_bytes)

        readable = raw_bytes.replace(b"Action: failed\xff\r\n", b"Action: failed\r\n")

        delivery_status = parse_delivery_status(readable)

        assert delivery_status.code == 550
        assert "550 5.1.1 User unknown\ufffd" in delivery_status.output
        assert delivery_status.final_recipient == "bob@example.net"

    def test_parse_delivery_status__final_recipient_falls_back_to_original_recipient(
        self,
    ):
        delivery_status = parse_delivery_status(
            make_dsn_email(
                final_recipient=None,
                original_recipient="rfc822; bob@example.net",
            )
        )

        assert delivery_status == DeliveryStatus(
            action=DsnAction.FAILED,
            code=550,
            output="smtp; 550 5.1.1 User unknown",
            final_recipient="bob@example.net",
        )

    def test_parse_delivery_status__final_recipient_strips_angle_addr(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(final_recipient="rfc822; <bob@example.net>")
        )

        assert delivery_status.final_recipient == "bob@example.net"

    def test_parse_delivery_status__final_recipient_strips_quoted_local_part(self):
        delivery_status = parse_delivery_status(
            make_dsn_email(final_recipient='rfc822; "Smith; Bob"@example.net')
        )

        assert delivery_status.final_recipient == "Smith; Bob@example.net"


@pytest.mark.django_db
class TestResolveBounceOwner:
    def test_resolve_bounce_owner__returns_message_for_verp_address(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)

        assert resolve_bounce_owner(mint_bounce_address(original)) == original

    def test_resolve_bounce_owner__matches_uppercased_sender_domain(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        local_part = mint_bounce_address(original).partition("@")[0]

        assert (
            resolve_bounce_owner(f"{local_part}@{domain.sender_domain.upper()}")
            == original
        )

    def test_resolve_bounce_owner__rejects_wrong_sender_domain(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        local_part = mint_bounce_address(original).partition("@")[0]

        assert resolve_bounce_owner(f"{local_part}@evil.test") is None

    def test_resolve_bounce_owner__returns_none_for_missing_signature(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)

        assert (
            resolve_bounce_owner(
                f"{settings.BOUNCE_LOCAL_PART}+{original.pk}@{domain.sender_domain}"
            )
            is None
        )

    def test_resolve_bounce_owner__returns_none_for_forged_signature(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        local_part = mint_bounce_address(original).partition("@")[0]
        rcpt_to = (
            f"{local_part[:-1]}{'B' if local_part[-1] == 'A' else 'A'}"
            f"@{domain.sender_domain}"
        )

        with CaptureQueriesContext(connection) as queries:
            resolved = resolve_bounce_owner(rcpt_to)

        assert resolved is None
        assert not queries.captured_queries

    def test_resolve_bounce_owner__returns_none_for_unknown_token(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        minted = mint_bounce_address(SimpleNamespace(pk=uuid.uuid4(), domain=domain))

        assert resolve_bounce_owner(minted) is None

    def test_resolve_bounce_owner__returns_none_for_malformed_token(self, org):
        domain = Domain.objects.create(name="example.com", org=org)

        assert (
            resolve_bounce_owner(
                f"{settings.BOUNCE_LOCAL_PART}+not-a-uuid@{domain.sender_domain}"
            )
            is None
        )

    def test_resolve_bounce_owner__returns_none_for_token_without_separator(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        rcpt_to = f"{settings.BOUNCE_LOCAL_PART}+no-separator@{domain.sender_domain}"

        assert resolve_bounce_owner(rcpt_to) is None

    def test_resolve_bounce_owner__returns_none_for_corrupted_token_bytes(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        value = base64.urlsafe_b64encode(b"truncated").rstrip(b"=").decode()
        signature = bounce_signer.signature(value)[:20]
        rcpt_to = (
            f"{settings.BOUNCE_LOCAL_PART}+{value}.{signature}@{domain.sender_domain}"
        )

        assert resolve_bounce_owner(rcpt_to) is None

    def test_resolve_bounce_owner__accepts_signature_from_fallback_key(
        self, org, monkeypatch
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        original = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        old_key = settings.SECRET_KEY + "pre-rotation"
        value = base64.urlsafe_b64encode(original.pk.bytes).rstrip(b"=").decode()
        signature = bounce_signer.signature(value, key=old_key)[:20]
        monkeypatch.setattr(bounce_signer, "fallback_keys", [old_key])
        rcpt_to = (
            f"{settings.BOUNCE_LOCAL_PART}+{value}.{signature}@{domain.sender_domain}"
        )

        assert resolve_bounce_owner(rcpt_to) == original

    def test_resolve_bounce_owner__returns_none_without_token(self, org):
        domain = Domain.objects.create(name="example.com", org=org)

        assert resolve_bounce_owner(f"alice@{domain.sender_domain}") is None


@pytest.mark.django_db(transaction=True)
class TestParseBounceReport:
    def test_parse_bounce_report__failed_action_bounces_and_suppresses(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )

        parse_bounce_report.func(message_pk=str(dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        transmission = Transmission.objects.get(message=outgoing)
        assert transmission.status == Transmission.Status.BOUNCED
        assert transmission.code == 550
        assert transmission.output == "smtp; 550 5.1.1 User unknown"
        assert SuppressionEntry.objects.filter(
            org=org,
            address_hash__email=outgoing.rcpt_to,
            reason=SuppressionEntry.Reason.BOUNCE,
        ).exists()

    def test_parse_bounce_report__delayed_action_records_retry_only(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_delayed_dsn_email(),
        )

        parse_bounce_report.func(message_pk=str(dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        transmission = Transmission.objects.get(message=outgoing)
        assert transmission.status == Transmission.Status.RETRY
        assert transmission.code == 421
        assert transmission.output == "smtp; 421 try again later"
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__delivered_action_records_nothing(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(action="delivered", status="2.0.0", diagnostic_code=""),
        )

        parse_bounce_report.func(message_pk=str(dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert not Transmission.objects.filter(message=outgoing).exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__unknown_owner_records_nothing(self, org, caplog):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            f"{settings.BOUNCE_LOCAL_PART}+{uuid.uuid4()}@{domain.sender_domain}",
            make_dsn_email(),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(dsn.pk))

        assert "matches no outgoing message" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert not Transmission.objects.exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)
        dsn.refresh_from_db()
        assert dsn.status == IncomingMessage.Status.RECEIVED

    def test_parse_bounce_report__unparseable_dsn_records_nothing(self, org, caplog):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(with_recipient_block=False),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(dsn.pk))

        assert "no parseable delivery status" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert not Transmission.objects.filter(message=outgoing).exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__failed_status_message_is_bounced(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(
            org, domain, status=OutgoingMessage.Status.FAILED
        )
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )

        parse_bounce_report.func(message_pk=str(dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        transmission = Transmission.objects.get(message=outgoing)
        assert transmission.status == Transmission.Status.BOUNCED
        assert SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__held_message_records_nothing(self, org, caplog):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(
            org, domain, status=OutgoingMessage.Status.HELD
        )
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(dsn.pk))

        assert "does not apply to outgoing message" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.HELD
        assert not Transmission.objects.filter(message=outgoing).exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__dsn_without_reporting_mta_bounces(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(with_reporting_mta=False),
        )

        parse_bounce_report.func(message_pk=str(dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        transmission = Transmission.objects.get(message=outgoing)
        assert transmission.status == Transmission.Status.BOUNCED
        assert transmission.code == 550
        assert SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__final_recipient_mismatch_records_nothing(
        self, org, caplog
    ):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(final_recipient="rfc822; carol@example.net"),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(dsn.pk))

        assert "does not report recipient" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert not Transmission.objects.filter(message=outgoing).exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__missing_final_recipient_records_nothing(
        self, org, caplog
    ):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(final_recipient=None),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(dsn.pk))

        assert "does not report recipient" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert not Transmission.objects.filter(message=outgoing).exists()
        assert not SuppressionEntry.objects.is_suppressed(org, outgoing.rcpt_to)

    def test_parse_bounce_report__second_delayed_dsn_records_single_retry(
        self, org, caplog
    ):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        first_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_delayed_dsn_email(),
        )
        second_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_delayed_dsn_email(),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(first_dsn.pk))
            parse_bounce_report.func(message_pk=str(second_dsn.pk))

        assert "repeats a recorded retry" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.SENT
        assert Transmission.objects.filter(message=outgoing).count() == 1
        assert (
            Transmission.objects.get(message=outgoing).status
            == Transmission.Status.RETRY
        )

    def test_parse_bounce_report__duplicate_failed_dsn_records_single_bounce(
        self, org, caplog
    ):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        first_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )
        second_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )

        with caplog.at_level(logging.WARNING):
            parse_bounce_report.func(message_pk=str(first_dsn.pk))
            parse_bounce_report.func(message_pk=str(second_dsn.pk))

        assert "does not apply to outgoing message" in caplog.text
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(message=outgoing).count() == 1
        assert (
            Transmission.objects.get(message=outgoing).status
            == Transmission.Status.BOUNCED
        )
        assert (
            SuppressionEntry.objects.filter(
                org=org,
                address_hash__email=outgoing.rcpt_to,
            ).count()
            == 1
        )

    def test_parse_bounce_report__delayed_dsn_after_bounce_records_nothing(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        failed_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_dsn_email(),
        )
        delayed_dsn = make_bounce_dsn(
            org,
            domain,
            mint_bounce_address(outgoing),
            make_delayed_dsn_email(),
        )

        parse_bounce_report.func(message_pk=str(failed_dsn.pk))
        parse_bounce_report.func(message_pk=str(delayed_dsn.pk))

        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(message=outgoing).count() == 1
        assert (
            Transmission.objects.get(message=outgoing).status
            == Transmission.Status.BOUNCED
        )


@pytest.mark.django_db(transaction=True)
class TestBounceReportChain:
    async def test_handle_data__failed_dsn_bounces_sent_message(self, org):
        domain = Domain.objects.get(org=org)
        outgoing = make_outgoing_message(org, domain, OutgoingMessage.Status.SENT)
        rcpt_to = mint_bounce_address(outgoing)
        envelope = SimpleNamespace(
            mail_from="mailer-daemon@mx.remote.example",
            rcpt_tos=[rcpt_to],
            content=make_dsn_email(),
            recipient_domain=domain,
        )
        session = SimpleNamespace(peer=("127.0.0.1", 1234), ssl=False)

        with patch(
            "abstract.mailauth.DmarcEvaluation.from_bytes",
            return_value=make_dmarc_evaluation(Disposition.NONE),
        ):
            result = await MXHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        outgoing.refresh_from_db()
        assert outgoing.status == OutgoingMessage.Status.BOUNCED
        transmission = Transmission.objects.get(message=outgoing)
        assert transmission.status == Transmission.Status.BOUNCED
        assert SuppressionEntry.objects.filter(
            org=org,
            address_hash__email=outgoing.rcpt_to,
            reason=SuppressionEntry.Reason.BOUNCE,
        ).exists()
