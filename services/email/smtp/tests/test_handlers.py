import base64
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from domains.models import Domain
from services.email.smtp.models import (
    OutgoingMessage,
    SmtpCredential,
    SuppressionEntry,
)


def make_email(mail_from, rcpt_to):
    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = rcpt_to
    message["Subject"] = "Test"
    message.set_content("Hello")
    return message


class TestHandleRcpt:
    async def test_handle_rcpt__appends_address(self):
        from services.email.smtp.handlers import SMTPHandler

        handler = SMTPHandler()
        envelope = SimpleNamespace(rcpt_tos=[])
        result = await handler.handle_RCPT(
            None, None, envelope, "bob@example.com", None
        )
        assert result == "250 OK"
        assert "bob@example.com" in envelope.rcpt_tos


class TestHandleData:
    async def test_handle_data__rejects_unauthenticated(self):
        from services.email.smtp.handlers import SMTPHandler

        handler = SMTPHandler()
        session = SimpleNamespace(credential=None, sender=None)
        result = await handler.handle_DATA(None, session, SimpleNamespace())
        assert result == "530 Authentication required"


class TestHandleAuth:
    async def test_handle_auth__unrecognized_type(self):
        from services.email.smtp.handlers import SMTPHandler

        handler = SMTPHandler()
        session = SimpleNamespace()
        result = await handler.handle_AUTH(None, session, None, ["LOGIN", "data"])
        assert result == "504 Unrecognized authentication type"

    async def test_handle_auth__malformed_plain(self):
        from services.email.smtp.handlers import SMTPHandler

        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(b"abc")
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "535 Authentication failed"

    @pytest.mark.django_db(transaction=True)
    async def test_handle_auth__wrong_key(self, user, org):
        from services.email.smtp.handlers import SMTPHandler

        SmtpCredential.objects.create_with_key(org=org, name="test")
        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(b"\0alice\0wrongkey12345678")
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "535 Authentication failed"

    @pytest.mark.django_db(transaction=True)
    async def test_handle_auth__success(self, user, org):
        from services.email.smtp.handlers import SMTPHandler

        _, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(f"\0alice\0{raw_key}".encode())
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "235 Authentication successful"
        assert session.credential is not None
        assert session.sender == user


@pytest.mark.django_db(transaction=True)
class TestProcessMessage:
    async def test_process_message__rejects_sender_domain_from_other_org(
        self,
        user,
        org,
        write_org,
    ):
        from services.email.smtp.handlers import process_message

        domain = Domain.objects.create(name="other.example.com", org=write_org)
        credential, _ = SmtpCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", user.email)

        result = await process_message(
            f"alice@{domain.name}",
            user.email,
            message.as_bytes(),
            message,
            credential,
            user,
            False,
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__rejects_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
        other_user,
    ):
        from services.email.smtp.handlers import process_message

        _, child = await Domain.objects.abulk_create(
            [
                Domain(name="example.com", org=org),
                Domain(name="app.example.com", org=write_org),
            ]
        )
        credential, _ = SmtpCredential.objects.create_with_key(org=write_org)
        mail_from = f"alice@{child.name}"
        message = make_email(mail_from, other_user.email)

        result = await process_message(
            mail_from,
            other_user.email,
            message.as_bytes(),
            message,
            credential,
            other_user,
            False,
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=write_org).aexists()

    async def test_process_message__rejects_external_recipient_without_billing(
        self,
        user,
        org,
    ):
        from services.email.smtp.handlers import process_message

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = SmtpCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", "external@example.com")

        result = await process_message(
            f"alice@{domain.name}",
            "external@example.com",
            message.as_bytes(),
            message,
            credential,
            user,
            False,
        )

        assert result == "550 Recipient not allowed without active billing"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__allows_member_recipient_case_insensitively(
        self,
        user,
        org,
    ):
        from services.email.smtp.handlers import process_message

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = SmtpCredential.objects.create_with_key(org=org)
        rcpt_to = user.email.upper()
        mail_from = f"alice@{domain.name.upper()}"
        message = make_email(mail_from, rcpt_to)

        with patch("services.email.smtp.handlers.deliver_message") as delivery_task:
            result = await process_message(
                mail_from,
                rcpt_to,
                message.as_bytes(),
                message,
                credential,
                user,
                True,
            )

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert outgoing.domain == domain
        assert outgoing.received_with_tls is True
        delivery_task.enqueue.assert_called_once_with(message_id=str(outgoing.id))

    async def test_process_message__allows_external_recipient_with_billing(
        self,
        user,
        org,
    ):
        from services.email.smtp.handlers import process_message

        org.billing_is_active = True
        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = SmtpCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", "external@example.com")

        with patch("services.email.smtp.handlers.deliver_message"):
            result = await process_message(
                f"alice@{domain.name}",
                "external@example.com",
                message.as_bytes(),
                message,
                credential,
                user,
                False,
            )

        assert result == "250 OK"
        assert await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__stores_suppressed_message_before_billing_check(
        self,
        user,
        org,
    ):
        from services.email.smtp.handlers import process_message

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = SmtpCredential.objects.create_with_key(org=org)
        rcpt_to = "suppressed@example.com"
        SuppressionEntry.objects.create_or_update(org=org, email=rcpt_to)
        message = make_email(f"alice@{domain.name}", rcpt_to)

        with patch("services.email.smtp.handlers.deliver_message") as delivery_task:
            result = await process_message(
                f"alice@{domain.name}",
                rcpt_to,
                message.as_bytes(),
                message,
                credential,
                user,
                False,
            )

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert outgoing.status == OutgoingMessage.Status.SUPPRESSED
        assert outgoing.domain == domain
        delivery_task.enqueue.assert_not_called()


@pytest.mark.django_db(transaction=True)
class TestAuthenticate:
    async def test_authenticate__finds_credential(self, user, org):
        from services.email.smtp.handlers import authenticate

        _, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate(user.username, raw_key)
        assert result is not None
        assert result.org == org

    async def test_authenticate__returns_none_for_wrong_key(self, user, org):
        from services.email.smtp.handlers import authenticate

        SmtpCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate(user.username, "wrongkey12345678")
        assert result is None

    async def test_authenticate__returns_none_for_unknown_user(self, user, org):
        from services.email.smtp.handlers import authenticate

        _, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate("unknownuser", raw_key)
        assert result is None

    async def test_authenticate__returns_none_for_held_credential(self, user, org):
        from services.email.smtp.handlers import authenticate

        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        cred.hold = True
        cred.save(update_fields=["hold"])
        result = await authenticate(user.username, raw_key)
        assert result is None
