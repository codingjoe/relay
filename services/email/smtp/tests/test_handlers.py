import base64
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from services.email.smtp.models import SmtpCredential


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
    async def test_process_message__free_domain_rejects_non_owner(self, user, org):
        from services.email.smtp.handlers import process_message

        cred, _ = SmtpCredential.objects.create_with_key(org=org)
        msg = EmailMessage()
        msg["From"] = f"{user.username}@open.localhost"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Hello")
        result = await process_message(
            f"{user.username}@open.localhost",
            "bob@example.com",
            msg.as_bytes(),
            msg,
            cred,
            user,
            False,
        )
        assert result == "550 Recipient not allowed for free sender domain"

    async def test_process_message__creates_outgoing_message(self, user, org):
        from services.email.smtp.handlers import process_message
        from services.email.smtp.models import OutgoingMessage

        cred, _ = SmtpCredential.objects.create_with_key(org=org)
        msg = EmailMessage()
        msg["From"] = "alice@example.com"
        msg["To"] = "bob@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Hello")
        result = await process_message(
            "alice@example.com",
            "bob@example.com",
            msg.as_bytes(),
            msg,
            cred,
            user,
            False,
        )
        assert result == "250 OK"
        assert OutgoingMessage.objects.filter(org=org, sender=user).count() == 1


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
