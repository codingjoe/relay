from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from domains.models import Domain
from services.email.msa.mcp import (
    InvalidRecipientError,
    InvalidSenderError,
    send_message,
)
from services.email.msa.models import OutgoingMessage, SuppressionEntry


@pytest.mark.django_db
class TestSendMessage:
    def test_send_message__stores_pending_message(
        self, user, org, django_capture_on_commit_callbacks
    ):
        domain = Domain.objects.get(org=org, is_managed=True)

        with (
            patch("services.email.msa.handlers.check_outgoing_spam") as spam_task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = send_message(
                from_email=f"billing@{domain.name}",
                to=user.email,
                subject="Hello",
                text="Hi there",
                user=user,
            )

        message = OutgoingMessage.objects.get(pk=result["message_id"])
        stored = message.parsed_email()
        assert message.status == OutgoingMessage.Status.PENDING
        assert message.mail_from == f"billing@{domain.name}"
        assert message.rcpt_to == user.email
        assert message.subject == "Hello"
        assert message.credential is None
        assert stored["Feedback-ID"] == f"{domain.sender_domain}:{org.pk}:tx:relay"
        assert any(name == "DKIM-Signature" for name, _value in message.headers)
        assert result["status"] == "pending"
        assert result["web_url"].endswith(message.get_absolute_url())
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(message.id), client_ip=""
        )

    def test_send_message__adds_html_body(
        self, user, org, django_capture_on_commit_callbacks
    ):
        domain = Domain.objects.get(org=org, is_managed=True)

        with (
            patch(
                "services.email.msa.handlers.sign_message",
                side_effect=lambda raw_bytes, domain: raw_bytes,
            ),
            patch("services.email.msa.handlers.check_outgoing_spam"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = send_message(
                from_email=f"billing@{domain.name}",
                to=user.email,
                subject="Hello",
                text="Hi there",
                html="<p>Hi there</p>",
                user=user,
            )

        message = OutgoingMessage.objects.get(pk=result["message_id"])
        assert message.text_body == b"Hi there\n"
        assert message.html_body.strip() == "<p>Hi there</p>"

    def test_send_message__stores_suppressed_message(self, user, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        recipient = "suppressed@example.com"
        SuppressionEntry.objects.create_or_update(org=org, email=recipient)

        result = send_message(
            from_email=f"billing@{domain.name}",
            to=recipient,
            subject="Hello",
            text="Hi there",
            user=user,
        )

        message = OutgoingMessage.objects.get(pk=result["message_id"])
        assert message.status == OutgoingMessage.Status.SUPPRESSED
        assert result["status"] == "suppressed"

    def test_send_message__rejects_sender_domain_of_another_org(self, user, write_org):
        domain = Domain.objects.get(org=write_org, is_managed=True)

        with pytest.raises(InvalidSenderError):
            send_message(
                from_email=f"billing@{domain.name}",
                to=user.email,
                subject="Hello",
                text="Hi there",
                user=user,
            )

    def test_send_message__rejects_unknown_sender_domain(self, user):
        with pytest.raises(InvalidSenderError):
            send_message(
                from_email="billing@unknown.example",
                to=user.email,
                subject="Hello",
                text="Hi there",
                user=user,
            )

    def test_send_message__rejects_invalid_recipient(self, user):
        with pytest.raises(InvalidRecipientError):
            send_message(
                from_email="billing@example.com",
                to="not-an-address",
                subject="Hello",
                text="Hi there",
                user=user,
            )

    def test_send_message__rejects_external_recipient_without_billing(self, user, org):
        org.billing_is_active = False
        org.save(update_fields=["billing_is_active"])
        domain = Domain.objects.get(org=org, is_managed=True)

        with pytest.raises(ToolError, match="billing"):
            send_message(
                from_email=f"billing@{domain.name}",
                to="external@example.com",
                subject="Hello",
                text="Hi there",
                user=user,
            )
