import base64
import re
import secrets
from email import message_from_bytes
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from domains.models import Domain
from services.email.msa.handlers import (
    ImplicitTLSHandler,
    SMTPHandler,
    add_feedback_id,
    authenticate,
    process_message,
    store_outgoing_message,
)
from services.email.msa.models import (
    MsaCredential,
    OutgoingMessage,
    SuppressionEntry,
    Transmission,
)


def make_email(mail_from, rcpt_to):
    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = rcpt_to
    message["Subject"] = "Test"
    message.set_content("Hello")
    return message


class TestAddFeedbackId:
    def test_add_feedback_id__prepends_org_feedback_id(self):
        message = make_email("alice@example.com", "bob@example.com")
        original = message.as_bytes()

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert result.endswith(original)
        header = re.fullmatch(
            rb"Feedback-ID: (9::[0-9a-f]{24}:relay)\r\n" + re.escape(original),
            result,
        )
        assert header
        assert feedback_id == header.group(1).decode()

    def test_add_feedback_id__replaces_customer_header(self):
        message = make_email("alice@example.com", "bob@example.com")
        message["Feedback-ID"] = "customer-id"
        original = message.as_bytes()

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert result.count(b"Feedback-ID:") == 1
        assert b"customer-id" not in result
        assert feedback_id.startswith("9::")
        body = original.split(b"\n\n", 1)[1]
        assert result.endswith(b"\n\n" + body)

    def test_add_feedback_id__removes_folded_customer_header(self):
        original = (
            b"From: alice@example.com\r\n"
            b"Feedback-ID: customer\r\n one\r\n"
            b"To: bob@example.com\r\n"
            b"\r\n"
            b"Hello"
        )

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert result.count(b"Feedback-ID:") == 1
        assert b"customer" not in result
        assert b" one" not in result
        assert feedback_id.startswith("9::")
        assert result.endswith(b"To: bob@example.com\r\n\r\nHello")

    def test_add_feedback_id__removes_every_customer_header(self):
        original = (
            b"Feedback-ID: first\r\n"
            b"Feedback-ID: second\r\n"
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"\r\n"
            b"Hello"
        )

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert result.count(b"Feedback-ID:") == 1
        assert b"first" not in result
        assert b"second" not in result
        assert feedback_id.startswith("9::")
        assert result.endswith(
            b"From: alice@example.com\r\nTo: bob@example.com\r\n\r\nHello"
        )

    def test_add_feedback_id__removes_obs_form_customer_header_with_fold(self):
        original = (
            b"From: alice@example.com\r\n"
            b"Feedback-ID : tenant\r\n"
            b"\tcontinuation\r\n"
            b"To: bob@example.com\r\n"
            b"\r\n"
            b"Hello"
        )

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert b"tenant" not in result
        assert b"continuation" not in result
        assert b"Feedback-ID: 9::" in result
        assert feedback_id.startswith("9::")
        assert result.endswith(b"To: bob@example.com\r\n\r\nHello")

    def test_add_feedback_id__keeps_lookalike_headers(self):
        original = (
            b"From: alice@example.com\r\n"
            b"X-Feedback-ID: x-tenant\r\n"
            b"Feedback-ID-Legacy: legacy\r\n"
            b"To: bob@example.com\r\n"
            b"\r\n"
            b"Hello"
        )

        result, feedback_id = add_feedback_id(original, SimpleNamespace(pk=9))

        assert b"X-Feedback-ID: x-tenant\r\n" in result
        assert b"Feedback-ID-Legacy: legacy\r\n" in result
        assert result.count(b"Feedback-ID: 9::") == 1
        assert feedback_id.startswith("9::")
        assert result.endswith(b"To: bob@example.com\r\n\r\nHello")


class TestHandleData:
    async def test_handle_data__rejects_unauthenticated(self):

        handler = SMTPHandler()
        session = SimpleNamespace(credential=None)
        result = await handler.handle_DATA(None, session, SimpleNamespace())
        assert result == "530 Authentication required"

    async def test_handle_auth__invalid_base64(self):

        handler = SMTPHandler()
        session = SimpleNamespace()
        result = await handler.handle_AUTH(None, session, None, ["PLAIN", "abc"])
        assert result == "535 Authentication failed"

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__stores_authenticated_submission(
        self,
        user,
        org,
    ):

        domain = await Domain.objects.aget(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        session = SimpleNamespace(
            credential=credential, peer=("127.0.0.1", 2525), ssl=True
        )
        message = make_email(f"alice@{domain.name}", user.email)
        envelope = SimpleNamespace(
            mail_from=f"alice@{domain.name}",
            rcpt_tos=[user.email],
            content=message.as_bytes(),
        )

        with patch("services.email.msa.handlers.check_outgoing_spam") as spam_task:
            result = await SMTPHandler().handle_DATA(None, session, envelope)

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert outgoing.received_with_tls is True
        stored = message_from_bytes(outgoing.raw_body.read())
        assert stored["Feedback-ID"].startswith(f"{org.pk}::")
        assert outgoing.feedback_id == stored["Feedback-ID"]
        assert outgoing.headers
        assert any(k == "Feedback-ID" for k, _ in outgoing.headers)
        assert any(k == "DKIM-Signature" for k, _ in outgoing.headers)
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(outgoing.id), client_ip="127.0.0.1"
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__stores_message_with_8bit_headers(
        self,
        user,
        org,
    ):

        domain = await Domain.objects.aget(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        session = SimpleNamespace(
            credential=credential, peer=("127.0.0.1", 2525), ssl=True
        )
        raw = (
            f"From: alice@{domain.name}\r\n"
            f"To: {user.email}\r\n"
            "Subject: Test\r\n"
            "X-Custom: caf\xe9\r\n"
            "\r\n"
            "Hello"
        ).encode("latin-1")
        envelope = SimpleNamespace(
            mail_from=f"alice@{domain.name}",
            rcpt_tos=[user.email],
            content=raw,
        )

        with patch("services.email.msa.handlers.check_outgoing_spam") as spam_task:
            result = await SMTPHandler().handle_DATA(None, session, envelope)

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert ["X-Custom", "caf\N{REPLACEMENT CHARACTER}"] in outgoing.headers
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(outgoing.id), client_ip="127.0.0.1"
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__replaces_existing_feedback_id(self, user, org):

        domain = await Domain.objects.aget(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        session = SimpleNamespace(
            credential=credential, peer=("127.0.0.1", 2525), ssl=True
        )
        message = make_email(f"alice@{domain.name}", user.email)
        message["Feedback-ID"] = "customer-id"
        envelope = SimpleNamespace(
            mail_from=f"alice@{domain.name}",
            rcpt_tos=[user.email],
            content=message.as_bytes(),
        )

        with patch("services.email.msa.handlers.check_outgoing_spam") as spam_task:
            result = await SMTPHandler().handle_DATA(None, session, envelope)

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        raw = outgoing.raw_body.read()
        stored = message_from_bytes(raw)
        assert b"customer-id" not in raw
        assert raw.count(b"Feedback-ID") == 1
        assert stored.get_all("Feedback-ID") == [outgoing.feedback_id]
        assert stored["Feedback-ID"].startswith(f"{org.pk}::")
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(outgoing.id), client_ip="127.0.0.1"
        )

    @pytest.mark.django_db(transaction=True)
    async def test_handle_data__accepts_string_content_without_peer(
        self,
        user,
        org,
    ):

        domain = await Domain.objects.aget(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        session = SimpleNamespace(credential=credential, peer=None)
        message = make_email(f"alice@{domain.name}", user.email)
        envelope = SimpleNamespace(
            mail_from=f"alice@{domain.name}",
            rcpt_tos=[user.email],
            content=message.as_string(),
        )

        with patch("services.email.msa.handlers.check_outgoing_spam"):
            result = await SMTPHandler().handle_DATA(None, session, envelope)

        assert result == "250 OK"
        assert await OutgoingMessage.objects.filter(org=org).aexists()


class TestHandleAuth:
    async def test_handle_auth__unrecognized_type(self):

        handler = SMTPHandler()
        session = SimpleNamespace()
        result = await handler.handle_AUTH(None, session, None, ["LOGIN", "data"])
        assert result == "504 Unrecognized authentication type"

    async def test_handle_auth__malformed_plain(self):

        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(b"abc")
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "535 Authentication failed"

    @pytest.mark.django_db(transaction=True)
    async def test_handle_auth__wrong_key(self, user, org):

        MsaCredential.objects.create_with_key(org=org, name="test")
        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(b"\0test-org\0wrongkey12345678")
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "535 Authentication failed"

    @pytest.mark.django_db(transaction=True)
    async def test_handle_auth__success(self, user, org):

        _, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        handler = SMTPHandler()
        session = SimpleNamespace()
        encoded = base64.b64encode(f"\0test-org\0{raw_key}".encode())
        result = await handler.handle_AUTH(
            None, session, None, ["PLAIN", encoded.decode()]
        )
        assert result == "235 Authentication successful"
        assert session.credential is not None


@pytest.mark.django_db(transaction=True)
class TestProcessMessage:
    async def test_process_message__rejects_mail_from_without_domain(
        self,
        user,
        org,
    ):

        credential, _ = MsaCredential.objects.create_with_key(org=org)
        message = make_email("noatsign", user.email)

        result = await process_message(
            "noatsign",
            user.email,
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__rejects_case_variant_domain_mismatch(
        self,
        user,
        org,
    ):

        await Domain.objects.abulk_create(
            [
                Domain(name="App.example.com", org=org),
                Domain(name="app.example.com", org=org),
            ]
        )
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        mail_from = "alice@app.example.com"
        message = make_email(mail_from, user.email)

        result = await process_message(
            mail_from,
            user.email,
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__rejects_sender_domain_from_other_org(
        self,
        user,
        org,
        write_org,
    ):

        domain = Domain.objects.create(name="other.example.com", org=write_org)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", user.email)

        result = await process_message(
            f"alice@{domain.name}",
            user.email,
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__rejects_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
        other_user,
    ):

        _, child = await Domain.objects.abulk_create(
            [
                Domain(name="example.com", org=org),
                Domain(name="app.example.com", org=write_org),
            ]
        )
        credential, _ = MsaCredential.objects.create_with_key(org=write_org)
        mail_from = f"alice@{child.name}"
        message = make_email(mail_from, other_user.email)

        result = await process_message(
            mail_from,
            other_user.email,
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Sender domain not registered"
        assert not await OutgoingMessage.objects.filter(org=write_org).aexists()

    async def test_process_message__rejects_external_recipient_without_billing(
        self,
        user,
        org,
    ):

        org.billing_is_active = False
        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", "external@example.com")

        result = await process_message(
            f"alice@{domain.name}",
            "external@example.com",
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Recipient not allowed without active billing"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__rejects_submission_when_org_locked(
        self,
        user,
        org,
    ):

        org.suspended_at = timezone.now()
        await org.asave(update_fields=["suspended_at", "modified_at"])
        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", user.email)

        result = await process_message(
            f"alice@{domain.name}",
            user.email,
            message.as_bytes(),
            credential,
            False,
            "",
        )

        assert result == "550 Account suspended due to sender reputation"
        assert not await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__allows_member_recipient_case_insensitively(
        self,
        user,
        org,
    ):

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        rcpt_to = user.email.upper()
        mail_from = f"alice@{domain.name.upper()}"
        message = make_email(mail_from, rcpt_to)

        with patch("services.email.msa.handlers.check_outgoing_spam") as spam_task:
            result = await process_message(
                mail_from,
                rcpt_to,
                message.as_bytes(),
                credential,
                True,
                "",
            )

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert outgoing.domain == domain
        assert outgoing.received_with_tls is True
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(outgoing.id), client_ip=""
        )

    async def test_process_message__allows_external_recipient_with_billing(
        self,
        user,
        org,
    ):

        org.billing_is_active = True
        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        message = make_email(f"alice@{domain.name}", "external@example.com")

        with patch("services.email.msa.handlers.check_outgoing_spam"):
            result = await process_message(
                f"alice@{domain.name}",
                "external@example.com",
                message.as_bytes(),
                credential,
                False,
                "",
            )

        assert result == "250 OK"
        assert await OutgoingMessage.objects.filter(org=org).aexists()

    async def test_process_message__stores_suppressed_message_before_billing_check(
        self,
        user,
        org,
    ):

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        rcpt_to = "suppressed@example.com"
        SuppressionEntry.objects.create_or_update(org=org, email=rcpt_to)
        message = make_email(f"alice@{domain.name}", rcpt_to)

        with patch("services.email.msa.handlers.check_outgoing_spam") as spam_task:
            result = await process_message(
                f"alice@{domain.name}",
                rcpt_to,
                message.as_bytes(),
                credential,
                False,
                "",
            )

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        assert outgoing.status == OutgoingMessage.Status.SUPPRESSED
        assert outgoing.feedback_id == ""
        assert b"Feedback-ID" not in outgoing.raw_body.read()
        assert outgoing.domain == domain
        spam_task.enqueue.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    async def test_process_message__suppressed_strips_customer_feedback_id(
        self,
        user,
        org,
    ):

        domain = Domain.objects.get(org=org, is_managed=True)
        credential, _ = MsaCredential.objects.create_with_key(org=org)
        rcpt_to = "suppressed@example.com"
        SuppressionEntry.objects.create_or_update(org=org, email=rcpt_to)
        message = make_email(f"alice@{domain.name}", rcpt_to)
        message["Feedback-ID"] = "customer-id"

        with patch("services.email.msa.handlers.check_outgoing_spam"):
            result = await process_message(
                f"alice@{domain.name}",
                rcpt_to,
                message.as_bytes(),
                credential,
                False,
                "",
            )

        outgoing = await OutgoingMessage.objects.aget(org=org)
        assert result == "250 OK"
        raw = outgoing.raw_body.read()
        assert b"customer-id" not in raw
        assert b"Feedback-ID" not in raw
        assert not any(name == "Feedback-ID" for name, _ in outgoing.headers)
        assert outgoing.feedback_id == ""


@pytest.mark.django_db
class TestStoreOutgoingMessage:
    def test_store_outgoing_message__pending_enqueues_spam_check(
        self,
        org,
        django_capture_on_commit_callbacks,
    ):

        domain = Domain.objects.get(org=org, is_managed=True)
        raw_bytes = make_email("alice@example.com", "bob@example.com").as_bytes()

        with (
            patch("services.email.msa.handlers.check_outgoing_spam") as spam_task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            message = store_outgoing_message(
                org=org,
                rcpt_to="bob@example.com",
                mail_from="alice@example.com",
                domain=domain,
                credential=None,
                status=OutgoingMessage.Status.PENDING,
                feedback_id="1::abc:relay",
                ssl=True,
                client_ip="192.0.2.1",
                raw_bytes=raw_bytes,
            )

        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip="192.0.2.1"
        )
        transmission = Transmission.objects.get(message=message)
        assert transmission.status == Transmission.Status.SUBMITTED

    def test_store_outgoing_message__suppressed_skips_spam_check(
        self,
        org,
        django_capture_on_commit_callbacks,
    ):

        domain = Domain.objects.get(org=org, is_managed=True)
        raw_bytes = make_email("alice@example.com", "bob@example.com").as_bytes()

        with (
            patch("services.email.msa.handlers.check_outgoing_spam") as spam_task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            message = store_outgoing_message(
                org=org,
                rcpt_to="bob@example.com",
                mail_from="alice@example.com",
                domain=domain,
                credential=None,
                status=OutgoingMessage.Status.SUPPRESSED,
                feedback_id="",
                ssl=False,
                client_ip="192.0.2.1",
                raw_bytes=raw_bytes,
            )

        spam_task.enqueue.assert_not_called()
        transmission = Transmission.objects.get(message=message)
        assert transmission.status == Transmission.Status.SUBMITTED

    def test_store_outgoing_message__derives_subject_and_message_id(self, org):

        domain = Domain.objects.get(org=org, is_managed=True)
        message = make_email("alice@example.com", "bob@example.com")
        message["Message-ID"] = "<store-test@example.com>"

        stored = store_outgoing_message(
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            domain=domain,
            credential=None,
            status=OutgoingMessage.Status.PENDING,
            feedback_id="1::abc:relay",
            ssl=False,
            client_ip="",
            raw_bytes=message.as_bytes(),
        )

        assert stored.subject == "Test"
        assert stored.message_id == "<store-test@example.com>"


@pytest.mark.django_db(transaction=True)
class TestAuthenticate:
    async def test_authenticate__finds_credential(self, user, org):

        _, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate(org.slug, raw_key)
        assert result is not None
        assert result.org == org

    async def test_authenticate__returns_none_for_wrong_key(self, user, org):

        MsaCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate(org.slug, "wrongkey12345678")
        assert result is None

    async def test_authenticate__returns_none_for_unknown_org(self, user, org):

        _, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        result = await authenticate("unknown-org", raw_key)
        assert result is None

    async def test_authenticate__returns_none_for_held_credential(self, user, org):

        cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        cred.hold = True
        cred.save(update_fields=["hold"])
        result = await authenticate(org.slug, raw_key)
        assert result is None

    async def test_authenticate__skips_credential_with_matching_prefix_but_wrong_key(
        self,
        user,
        org,
    ):

        # Iterate-then-fail requires the stale credential to come first,
        # so mint the key here and create the stale credential before it.
        raw_key = secrets.token_urlsafe(15)
        stale = MsaCredential(org=org, name="stale")
        stale.set_key(raw_key[:8] + "stale-tail")
        stale.save()
        credential = MsaCredential(org=org, name="test")
        credential.set_key(raw_key)
        credential.save()

        result = await authenticate(org.slug, raw_key)
        assert result is not None
        assert result.name == "test"


class TestImplicitTLSHandler:
    async def test_handle_data__marks_session_encrypted(self):

        handler = ImplicitTLSHandler()
        session = SimpleNamespace(credential=None, ssl=False)
        result = await handler.handle_DATA(None, session, SimpleNamespace())
        assert result == "530 Authentication required"
        assert session.ssl is True
