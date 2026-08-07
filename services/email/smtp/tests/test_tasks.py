from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile

from domains.models import Domain
from services.email.smtp.models import OutgoingMessage, Transmission


class TestFetchMxHosts:
    def test_fetch_mx_hosts__sorted_by_priority(self, dns_resolver):
        from services.email.smtp.tasks import fetch_mx_hosts

        dns_resolver.add(
            "example.com", "MX", "20 mx2.example.com.", "10 mx1.example.com."
        )
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx1.example.com", "mx2.example.com"]

    def test_fetch_mx_hosts__strips_trailing_dot(self, dns_resolver):
        from services.email.smtp.tasks import fetch_mx_hosts

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx.example.com"]

    def test_fetch_mx_hosts__empty_on_error(self):
        from services.email.smtp.tasks import fetch_mx_hosts

        assert fetch_mx_hosts("nonexistent.invalid") == []


@pytest.mark.django_db(transaction=True)
class TestDeliverMessage:
    def test_deliver_message__no_mx_records(self, user, org, dns_resolver):
        from services.email.smtp.tasks import deliver_message

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@nowhere.invalid",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        deliver_message.func(
            message_id=str(msg.id),
            rcpt_to="bob@nowhere.invalid",
            mail_from="alice@example.com",
            domain_id=None,
        )

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(message=msg).count() == 1
        t = Transmission.objects.get(message=msg)
        assert t.status == Transmission.Status.FAILED
        assert "No MX" in t.details

    def test_deliver_message__with_domain_signs_and_sends(
        self, user, org, dns_resolver
    ):
        from services.email.smtp.tasks import deliver_message

        domain = Domain.objects.create(name="example.com", org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        mock_response = MagicMock()
        mock_response.__str__ = MagicMock(return_value="250 OK")

        with (
            patch(
                "services.email.smtp.tasks.aiosmtplib.send", return_value=mock_response
            ),
            patch("domains.dkim.sign_message", return_value=b"signed") as mock_sign,
        ):
            deliver_message.func(
                message_id=str(msg.id),
                rcpt_to="bob@example.com",
                mail_from="alice@example.com",
                domain_id=domain.pk,
            )

        mock_sign.assert_called_once()
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SENT
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.SENT
        ).exists()

    def test_deliver_message__permanent_failure_marks_bounced(
        self, user, org, dns_resolver
    ):
        import aiosmtplib

        from services.email.smtp.tasks import deliver_message

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="reject@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        exc = aiosmtplib.SMTPResponseException(550, b"User unknown")
        with patch("services.email.smtp.tasks.aiosmtplib.send", side_effect=exc):
            deliver_message.func(
                message_id=str(msg.id),
                rcpt_to="reject@example.com",
                mail_from="alice@example.com",
                domain_id=None,
            )

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.BOUNCED
        ).exists()
