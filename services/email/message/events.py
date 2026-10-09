"""Build the flat payload webhook receivers and MCP clients read."""

from dataclasses import dataclass

from .models import Message, Transmission


@dataclass
class MessageEvent:
    """Carry one mail's routing, TLS, and spam fields, without the raw body."""

    message_id: str
    sender: str
    recipient: str
    subject: str
    rfc822_message_id: str
    received_with_tls: bool
    receiving_domain: str
    body_url: str | None
    spam_score: float | None = None
    spam_action: str = ""

    @classmethod
    def from_message(cls, message: Message) -> MessageEvent:
        """Return the flat fields for one stored mail."""
        reception = next(
            (
                transmission
                for transmission in message.transmissions.all()
                if transmission.status == Transmission.Status.RECEIVED
            ),
            None,
        )
        # A merged base instance keeps the receiving domain behind the parent link.
        receiving_domain = getattr(message, "receiving_domain", None)
        if receiving_domain is None:
            receiving_domain = getattr(
                getattr(message, "incomingmessage", None), "receiving_domain", ""
            )
        return cls(
            message_id=str(message.id),
            sender=message.mail_from,
            recipient=message.rcpt_to,
            subject=message.subject,
            rfc822_message_id=message.message_id,
            received_with_tls=(
                reception is not None
                and reception.tls_mode != Transmission.TlsMode.PLAINTEXT
            ),
            receiving_domain=receiving_domain,
            body_url=message.raw_body.url if message.raw_body else None,
            spam_score=message.spam_score,
            spam_action=message.spam_action,
        )
