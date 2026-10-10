import json
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ResourceError, ValidationError
from fastmcp.resources import resource
from fastmcp.server.auth import require_scopes
from fastmcp.tools import tool
from pydantic import Field

from abstract.mcp import paginate_queryset
from abstract.scopes import Scope, scopes
from accounts.mcp import authenticated_user

from .events import MessageEvent
from .models import Message


@scopes.register
class MessageScope(Scope):
    """Grant access to one organization's mail."""

    read = "messages:read", _("View sent and received messages.")
    write = "messages:write", _("Send new messages.")


class InvalidStatusError(ValidationError):
    """Signal a filter value no concrete subclass declares."""

    def __init__(self, status: str) -> None:
        super().__init__(f"Invalid status: {status}")


class MessageNotFoundError(ResourceError):
    """Signal an id that resolves for no organization the caller belongs to."""

    def __init__(self) -> None:
        super().__init__("Message not found or not accessible.")


class MessageDirection(StrEnum):
    """Restrict a listing to sent or received mail."""

    ALL = "all"
    SENT = "sent"
    RECEIVED = "received"


def describe_message(message: Message) -> dict[str, object]:
    """Return the flat fields plus the kind and status labels."""
    return MessageEvent.from_message(message).__dict__ | {
        "kind": message.kind,
        "kind_display": str(message.kind_display),
        "status": message.status,
        "status_display": str(message.status_display),
    }


@tool(auth=require_scopes(MessageScope.read))
def list_messages(
    direction: MessageDirection = MessageDirection.ALL,
    email: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    page_size: Annotated[int, Field(ge=1, le=100)] = 25,
    user: User = Depends(authenticated_user),  # noqa: B008 -- dependency
) -> tuple[list[dict[str, object]], str | None]:
    """
    Return the sent and received mail of the user's organizations, newest first.

    Args:
        direction: Restrict the page to sent or received mail.
        email: Match senders and recipients containing this text.
        status: Restrict the page to one message status.
        cursor: Continue from the cursor a previous page returned.
        page_size: Number of messages per page, up to 100.
        user: The active user the access token was issued for.

    """
    if status and status not in dict(Message.status_choices()):
        raise InvalidStatusError(status)
    queryset = Message.objects.filter(org__in=user.organizations.all())
    match direction:
        case MessageDirection.SENT:
            queryset = queryset.filter(content_type__model="outgoingmessage")
        case MessageDirection.RECEIVED:
            queryset = queryset.filter(content_type__model="incomingmessage")
    if email:
        queryset = queryset.filter(
            Q(mail_from__icontains=email) | Q(rcpt_to__icontains=email)
        )
    if status:
        queryset = queryset.filter(
            Q(outgoingmessage__status=status) | Q(incomingmessage__status=status)
        )
    page, next_cursor = paginate_queryset(
        queryset.select_related("content_type", "incomingmessage")
        .prefetch_related("transmissions")
        .order_by("-id"),
        cursor,
        page_size,
    )
    return (
        [
            describe_message(message) | {"created_at": message.created_at.isoformat()}
            for message in page
        ],
        next_cursor,
    )


@resource(
    "relay://email/messages/{message_id}",
    mime_type="application/json",
    auth=require_scopes(MessageScope.read),
)
def get_message(
    message_id: UUID,
    user: User = Depends(authenticated_user),  # noqa: B008 -- dependency
) -> str:
    """
    Return one mail with its headers, scan verdicts, and delivery summary.

    Args:
        message_id: Identifier of the message to return.
        user: The active user the access token was issued for.

    """
    try:
        message = (
            Message.objects.select_related("content_type", "org", "incomingmessage")
            .prefetch_related("transmissions")
            .get(id=message_id, org__in=user.organizations.all())
        )
    except Message.DoesNotExist as error:
        raise MessageNotFoundError from error
    transmissions = list(message.transmissions.all())
    delivery_finished_at = max(
        (transmission.finished_at for transmission in transmissions), default=None
    )
    return json.dumps(
        describe_message(message)
        | {
            "headers": message.parsed_headers,
            "virus_action": message.virus_action,
            "virus_name": message.virus_name,
            "virus_symbols": message.virus_symbols,
            "delivery_attempts": len(transmissions),
            "delivery_finished_at": delivery_finished_at,
            "delivery_duration_secs": (
                (delivery_finished_at - message.created_at).total_seconds()
                if delivery_finished_at
                else None
            ),
            "created_at": message.created_at,
            # The MCP base URL is the public origin that also serves the web app.
            "web_url": f"{settings.RELAY_MCP_BASE_URL}{message.get_absolute_url()}",
        },
        cls=DjangoJSONEncoder,
    )
