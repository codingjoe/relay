"""Expose outgoing mail submissions to MCP clients."""

from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import require_scopes
from fastmcp.tools import tool

from accounts.mcp import get_authenticated_user
from domains.models import Domain, canonicalize_domain_name
from services.email.message.mcp import MessageScope

from .handlers import SubmissionRejectedError, submit_outgoing_message


class InvalidSenderError(ToolError):
    """Signal a sender address relay cannot use for the caller."""

    def __init__(self) -> None:
        super().__init__(
            "The sender address must use a domain of an organization you belong to."
        )


class InvalidRecipientError(ToolError):
    """Signal a recipient address relay cannot parse."""

    def __init__(self) -> None:
        super().__init__("The recipient address is invalid.")


class InvalidMessageError(ToolError):
    """Signal a message relay cannot build from the input."""

    def __init__(self, error: ValueError) -> None:
        super().__init__(f"Invalid message header: {error}")


def create_raw_message(
    *,
    mail_from: str,
    rcpt_to: str,
    subject: str,
    text: str,
    html: str | None,
) -> bytes:
    """Return an RFC 5322 message with a text and optional HTML body."""
    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = rcpt_to
    message["Subject"] = subject
    message["Date"] = format_datetime(timezone.now())
    message["Message-ID"] = make_msgid(domain=mail_from.rsplit("@", 1)[-1])
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message.as_bytes()


@tool(auth=require_scopes(MessageScope.send))
def send_message(
    from_email: str,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    user: User = Depends(get_authenticated_user),  # noqa: B008 -- dependency
) -> dict[str, object]:
    """
    Send one email from a domain of the user's organizations.

    The sender domain must be registered to an organization the user belongs
    to. relay signs the message and queues it for delivery.

    Args:
        from_email: Sender address on a domain of an organization the user belongs to.
        to: Recipient address.
        subject: Subject line.
        text: Plain text body.
        html: Optional HTML body.
        user: The active user the access token was issued for.

    """
    mail_from = parseaddr(from_email)[1]
    rcpt_to = parseaddr(to)[1]
    if not mail_from or "@" not in mail_from:
        raise InvalidSenderError
    if not rcpt_to or "@" not in rcpt_to:
        raise InvalidRecipientError

    try:
        domain = Domain.objects.select_related("org").get(
            name=canonicalize_domain_name(mail_from.rsplit("@", 1)[1])
        )
    except (Domain.DoesNotExist, ValidationError) as error:
        raise InvalidSenderError from error

    if not domain.org.members.filter(pk=user.pk).exists():
        raise InvalidSenderError

    try:
        raw_message = create_raw_message(
            mail_from=mail_from,
            rcpt_to=rcpt_to,
            subject=subject,
            text=text,
            html=html,
        )
    except ValueError as error:
        raise InvalidMessageError(error) from error

    try:
        message = submit_outgoing_message(
            org=domain.org,
            mail_from=mail_from,
            rcpt_to=rcpt_to,
            raw_bytes=raw_message,
            credential=None,
            ssl=True,
            client_ip="",
            started_at=timezone.now(),
        )
    except SubmissionRejectedError as error:
        raise ToolError(str(error)) from error

    return {
        "message_id": str(message.id),
        "status": message.status,
        "status_display": str(message.status_display),
        "web_url": f"{settings.MCP_BASE_URL}{message.get_absolute_url()}",
    }
