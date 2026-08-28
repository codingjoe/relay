from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.base import ContentFile

from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission


class TestFetchMxHosts:
    def test_fetch_mx_hosts__sorted_by_priority(self, dns_resolver):
        from services.email.msa.tasks import fetch_mx_hosts

        dns_resolver.add(
            "example.com", "MX", "20 mx2.example.com.", "10 mx1.example.com."
        )
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx1.example.com", "mx2.example.com"]

    def test_fetch_mx_hosts__strips_trailing_dot(self, dns_resolver):
        from services.email.msa.tasks import fetch_mx_hosts

        dns_resolver.add("example.com", "MX", "10 mx.example.com.")
        hosts = fetch_mx_hosts("example.com")
        assert hosts == ["mx.example.com"]

    def test_fetch_mx_hosts__empty_on_error(self):
        from services.email.msa.tasks import fetch_mx_hosts

        assert fetch_mx_hosts("nonexistent.invalid") == []


@pytest.mark.django_db(transaction=True)
class TestDeliverMessage:
    def test_deliver_message__no_mx_records(self, user, org, dns_resolver):
        from services.email.msa.tasks import deliver_message

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@nowhere.invalid",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        with patch("domains.dkim.sign_message", return_value=b"signed"):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(message=msg).count() == 1
        t = Transmission.objects.get(message=msg)
        assert t.status == Transmission.Status.FAILED
        assert "No MX" in t.details

    def test_deliver_message__with_domain_signs_and_sends(
        self, user, org, dns_resolver
    ):
        from services.email.msa.tasks import deliver_message

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
        mock_response = MagicMock()
        mock_response.__str__ = MagicMock(return_value="250 OK")

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.send", return_value=mock_response
            ) as mock_send,
            patch("domains.dkim.sign_message", return_value=b"signed") as mock_sign,
        ):
            deliver_message.func(message_id=str(msg.id))

        mock_sign.assert_called_once()
        assert mock_send.call_args.kwargs["sender"] == (
            f"{settings.RELAY_BOUNCE_LOCAL_PART}+{msg.id}@{domain.sender_domain}"
        )
        assert (
            mock_send.call_args.kwargs["local_hostname"]
            == settings.RELAY_SMTP_PUBLIC_HOSTNAME
        )
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.SENT
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.SENT
        ).exists()

    def test_deliver_message__permanent_failure_marks_bounced(
        self, user, org, dns_resolver
    ):
        import aiosmtplib

        from services.email.msa.tasks import deliver_message

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
        with (
            patch("services.email.msa.tasks.aiosmtplib.send", side_effect=exc),
            patch("domains.dkim.sign_message", return_value=b"signed"),
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.BOUNCED
        assert Transmission.objects.filter(
            message=msg, status=Transmission.Status.BOUNCED
        ).exists()

    def test_deliver_message__fails_closed_without_sender_domain(self, user, org):
        from services.email.msa.tasks import deliver_message

        msg = OutgoingMessage.objects.create(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=None,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        with patch("services.email.msa.tasks.aiosmtplib.send") as mock_send:
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="no sender domain",
        ).exists()
        mock_send.assert_not_called()

    def test_deliver_message__fails_closed_for_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
        other_user,
    ):
        from services.email.msa.tasks import deliver_message

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

        with (
            patch("domains.dkim.sign_message") as mock_sign,
            patch("services.email.msa.tasks.aiosmtplib.send") as mock_send,
        ):
            deliver_message.func(message_id=str(msg.id))

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="ambiguous",
        ).exists()
        mock_sign.assert_not_called()
        mock_send.assert_not_called()

    def test_deliver_message__drops_message_of_locked_org(self, user, org):
        from services.email.msa.tasks import deliver_message

        domain = Domain.objects.get(org=org)
        message = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        message.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        message.save()

        org.reputation_locked = True
        org.save(update_fields=["reputation_locked", "modified_at"])

        with patch("services.email.msa.tasks.aiosmtplib.send") as mock_send:
            deliver_message.func(message_id=str(message.id))

        mock_send.assert_not_called()
        message.refresh_from_db()
        assert message.status == OutgoingMessage.Status.DROPPED
        assert not Transmission.objects.filter(message=message).exists()


@pytest.mark.django_db(transaction=True)
class TestCheckOutgoingSpam:
    def test_check_outgoing_spam__drops_queued_messages_of_locked_org(self, user, org):
        from services.email.msa.tasks import check_outgoing_spam

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()

        org.reputation_locked = True
        org.save(update_fields=["reputation_locked", "modified_at"])

        check_outgoing_spam.func(message_pk=str(msg.id), client_ip="")

        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.DROPPED
        assert not Transmission.objects.filter(message=msg).exists()

    def test_check_outgoing_spam__holds_spam(self, user, org):
        from services.email.msa.tasks import check_outgoing_spam
        from services.email.spam import SpamAction, SpamResult

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
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
        from services.email.msa.tasks import check_outgoing_spam
        from services.email.spam import SpamResult

        domain = Domain.objects.get(org=org)
        msg = OutgoingMessage.objects.create(
            sender=user,
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


@pytest.mark.django_db(transaction=True)
class TestDeliverMessageFailureModes:
    @staticmethod
    def make_message(user, org, domain, rcpt_to="bob@example.com"):
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to=rcpt_to,
            mail_from="alice@example.com",
            domain=domain,
        )
        msg.raw_body.save("test.eml", ContentFile(b"test"), save=False)
        msg.save()
        return msg

    def test_deliver_message__fails_for_non_canonical_sender_domain(self, user, org):
        from services.email.msa.tasks import deliver_message

        # bulk_create bypasses save()/clean(), so the stored name stays
        # non-canonical and no longer matches the resolved root domain.
        (domain,) = Domain.objects.bulk_create([Domain(name="Example.com", org=org)])
        msg = self.make_message(user, org, domain)

        with (
            patch("domains.dkim.sign_message") as mock_sign,
            patch("services.email.msa.tasks.aiosmtplib.send") as mock_send,
        ):
            deliver_message.func(message_id=str(msg.id))

        mock_sign.assert_not_called()
        mock_send.assert_not_called()
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
        from services.email.msa.tasks import deliver_message

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        with (
            patch("services.email.msa.tasks.MtaStsPolicy") as mock_policy,
            patch("services.email.msa.tasks.aiosmtplib.send") as mock_send,
            patch("domains.dkim.sign_message", return_value=b"signed"),
        ):
            mock_policy.get.return_value.allows.return_value = (
                False,
                "STS policy blocked",
            )
            deliver_message.func(message_id=str(msg.id))

        mock_policy.get.return_value.allows.assert_called_once_with("mx.example.com")
        mock_send.assert_not_called()
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
        import aiosmtplib

        from services.email.msa.tasks import deliver_message

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add("example.com", "MX", "10 mx.example.com.")

        exc = aiosmtplib.SMTPResponseException(450, b"Try again later")
        with (
            patch("services.email.msa.tasks.aiosmtplib.send", side_effect=exc),
            patch("domains.dkim.sign_message", return_value=b"signed"),
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
        import aiosmtplib

        from services.email.msa.tasks import deliver_message

        domain = Domain.objects.create(name="example.com", org=org)
        msg = self.make_message(user, org, domain)
        dns_resolver.add(
            "example.com", "MX", "10 mx1.example.com.", "20 mx2.example.com."
        )

        with (
            patch(
                "services.email.msa.tasks.aiosmtplib.send",
                side_effect=aiosmtplib.SMTPException("nope"),
            ) as mock_send,
            patch("domains.dkim.sign_message", return_value=b"signed"),
        ):
            deliver_message.func(message_id=str(msg.id))

        assert mock_send.call_count == 2
        msg.refresh_from_db()
        assert msg.status == OutgoingMessage.Status.FAILED
        assert Transmission.objects.filter(
            message=msg,
            status=Transmission.Status.FAILED,
            details__contains="All MX hosts failed for example.com",
        ).exists()
