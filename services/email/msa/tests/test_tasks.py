import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.msa.tasks import (
    check_outgoing_spam,
    deliver_message,
    fetch_mx_hosts,
)
from services.email.spam import SpamAction, SpamResult


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

    def test_fetch_mx_hosts__empty_on_error(self):
        assert fetch_mx_hosts("nonexistent.invalid") == []


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

        deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(message=msg).count() == 1
        t = Transmission.objects.get(message=msg)
        assert t.status == Transmission.Status.FAILED
        assert "No MX" in t.details

    def test_deliver_message__sends_with_bounce_return_path(
        self, user, org, dns_resolver
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
        certificate = make_certificate("mx.example.com")
        ssl_object = MagicMock()
        ssl_object.get_unverified_chain.return_value = [
            certificate.public_bytes(Encoding.DER)
        ]
        smtp_client = MagicMock()
        smtp_client.sendmail = AsyncMock(return_value="250 OK")
        smtp_client.connect = AsyncMock()
        smtp_client.close = MagicMock()
        smtp_client.use_tls = False
        smtp_client.get_transport_info.side_effect = {
            "ssl_object": ssl_object,
            "cipher": ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 32),
        }.get
        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            return_value=smtp_client,
        ) as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        assert (
            mock_smtp.call_args.kwargs["local_hostname"]
            == settings.RELAY_SMTP_PUBLIC_HOSTNAME
        )
        assert smtp_client.sendmail.call_args.args[0] == (
            f"{settings.RELAY_BOUNCE_LOCAL_PART}+{msg.id}@{domain.sender_domain}"
        )
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SENT
        transmission = Transmission.objects.get(
            message=msg, status=Transmission.Status.SENT
        )
        assert transmission.mx_host == "mx.example.com"
        assert transmission.tls_mode == Transmission.TlsMode.STARTTLS
        assert transmission.tls_version == "TLSv1.3"
        assert transmission.tls_cipher == "TLS_AES_256_GCM_SHA384"
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
        assert stored_certificate.chain == [stored_certificate]

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

    @staticmethod
    def make_message(user, org, domain, rcpt_to="bob@example.com"):
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to=rcpt_to,
            mail_from="alice@example.com",
            domain=domain,
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
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="All MX hosts failed",
        ).exists()

    def test_deliver_message__temporary_smtp_error_fails_message(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        exc = aiosmtplib.SMTPResponseException(450, b"Try again later")
        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            side_effect=exc,
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.FAILED
        ).exists()

    def test_deliver_message__exhausts_all_mx_hosts_on_smtp_exception(
        self, user, org, dns_resolver
    ):

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )

        with patch(
            "services.email.msa.tasks.aiosmtplib.SMTP",
            side_effect=aiosmtplib.SMTPException("nope"),
        ) as mock_smtp:
            deliver_message.func(message_id=str(msg.id))

        assert mock_smtp.call_count == 2
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="All MX hosts failed for example.com",
        ).exists()


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
