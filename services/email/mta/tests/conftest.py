from email import message_from_bytes
from email.message import EmailMessage, Message

from abstract.mailauth import Alignment, AuthResult, Disposition, DmarcEvaluation


def make_raw_email(subject: str = "Postmaster alert") -> bytes:
    """Return a raw inbound email for the postmaster address."""
    msg = EmailMessage()
    msg["From"] = "external@example.org"
    msg["To"] = "postmaster@example.com"
    msg["Subject"] = subject
    msg.set_content("Something happened")
    return to_crlf(msg.as_bytes())


def make_dmarc_evaluation(
    disposition: Disposition = Disposition.NONE, **overrides: object
) -> DmarcEvaluation:
    """Return a passing DMARC evaluation, with overrides applied."""
    fields = {
        "source_ip_address": "192.0.2.1",
        "header_from": "example.org",
        "envelope_from": "example.org",
        "dkim_domain": "example.org",
        "dkim_result": AuthResult.PASS,
        "dkim_alignment": Alignment.PASS,
        "spf_domain": "example.org",
        "spf_result": AuthResult.PASS,
        "spf_alignment": Alignment.PASS,
        "disposition": disposition,
        "dmarc_policy_is_published": True,
    }
    fields.update(overrides)
    return DmarcEvaluation(**fields)


def to_crlf(raw: bytes) -> bytes:
    """Return the message bytes with every line ending on CRLF."""
    return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def make_dsn_email(
    action: str = "failed",
    status: str = "5.1.1",
    diagnostic_code: str = "smtp; 550 5.1.1 User unknown",
    with_recipient_block: bool = True,
    with_reporting_mta: bool = True,
    final_recipient: str | None = "rfc822; bob@example.net",
    original_recipient: str | None = None,
) -> bytes:
    """
    Return a raw RFC 3464 delivery status notification.

    The `message/delivery-status` part carries a per-message block and a
    per-recipient block, unless either is disabled. The blocks are real
    header-field objects, so the generator serializes them the way the
    email package parses one back in.
    """
    message = EmailMessage()
    message["From"] = "Mail Delivery System <mailer-daemon@mx.remote.example>"
    message["To"] = "bounce@relay.example"
    message["Subject"] = "Undelivered Mail Returned to Sender"
    message["Message-ID"] = "<dsn-1@mx.remote.example>"
    message.set_content("The recipient could not be reached.")
    message.make_mixed()
    message.set_type("multipart/report")
    message.set_param("report-type", "delivery-status")

    dsn_part = Message()
    dsn_part["Content-Type"] = "message/delivery-status"
    blocks = []
    if with_reporting_mta:
        per_message = Message()
        per_message["Reporting-MTA"] = "dns; mx.remote.example"
        blocks.append(per_message)
    if with_recipient_block:
        fields = {
            "Final-Recipient": final_recipient,
            "Original-Recipient": original_recipient,
            "Action": action,
            "Status": status,
            "Diagnostic-Code": diagnostic_code,
        }
        per_recipient = Message()
        for name, value in fields.items():
            if value:
                per_recipient[name] = value
        blocks.append(per_recipient)
    dsn_part.set_payload(blocks)
    message.attach(dsn_part)

    bounced = EmailMessage()
    bounced["From"] = "alice@example.com"
    bounced["To"] = "bob@example.net"
    bounced["Subject"] = "Hello"
    bounced.set_content("Hi")
    rfc822_part = Message()
    rfc822_part["Content-Type"] = "message/rfc822"
    rfc822_part.set_payload([message_from_bytes(bounced.as_bytes())])
    message.attach(rfc822_part)
    return to_crlf(message.as_bytes())


def make_arf_email(recipient: str) -> bytes:
    """Return a raw RFC 5965 feedback report addressed to a bounce address."""
    message = EmailMessage()
    message["From"] = "feedback@gmail.com"
    message["To"] = recipient
    message["Subject"] = "FBL Report"
    message.set_content("This is an authentication failure report.")
    message.make_mixed()
    message.set_type("multipart/report")
    message.set_param("report-type", "feedback-report")
    message.add_attachment(
        b"Feedback-Type: abuse\r\nUser-Agent: Gmail/FBL\r\nVersion: 1.0\r\n",
        maintype="message",
        subtype="feedback-report",
        cte="7bit",
    )
    return to_crlf(message.as_bytes())


def make_delayed_dsn_email() -> bytes:
    """Return a raw DSN reporting a temporary delivery delay."""
    return make_dsn_email(
        action="delayed",
        status="4.4.1",
        diagnostic_code="smtp; 421 try again later",
    )
