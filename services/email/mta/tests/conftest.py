from email.message import EmailMessage

from abstract.mailauth import Alignment, AuthResult, Disposition, DmarcEvaluation


def make_raw_email(subject: str = "Postmaster alert") -> bytes:
    """Return a raw inbound email for the postmaster address."""
    msg = EmailMessage()
    msg["From"] = "external@example.org"
    msg["To"] = "postmaster@example.com"
    msg["Subject"] = subject
    msg.set_content("Something happened")
    return msg.as_bytes()


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


def make_recipient_block(
    action: str,
    status: str,
    diagnostic_code: str,
    final_recipient: str | None = "rfc822; bob@example.net",
    original_recipient: str | None = None,
) -> str:
    """Return one per-recipient block of a delivery status part."""
    fields = {
        "Final-Recipient": final_recipient,
        "Original-Recipient": original_recipient,
        "Action": action,
        "Status": status,
        "Diagnostic-Code": diagnostic_code,
    }
    return "".join(f"{name}: {value}\r\n" for name, value in fields.items() if value)


def make_dsn_email(
    action: str = "failed",
    status: str = "5.1.1",
    diagnostic_code: str = "smtp; 550 5.1.1 User unknown",
    with_recipient_block: bool = True,
    with_reporting_mta: bool = True,
    final_recipient: str | None = "rfc822; bob@example.net",
    original_recipient: str | None = None,
) -> bytes:
    """Return a raw RFC 3464 delivery status notification.

    The `message/delivery-status` part carries a per-message block and a
    per-recipient block, unless either is disabled.
    """
    blocks = []
    if with_reporting_mta:
        blocks.append("Reporting-MTA: dns; mx.remote.example\r\n")
    if with_recipient_block:
        blocks.append(
            make_recipient_block(
                action, status, diagnostic_code, final_recipient, original_recipient
            )
        )
    delivery_status = "\r\n".join(blocks)
    return (
        "From: Mail Delivery System <mailer-daemon@mx.remote.example>\r\n"
        "To: bounce@relay.example\r\n"
        "Subject: Undelivered Mail Returned to Sender\r\n"
        "Message-ID: <dsn-1@mx.remote.example>\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: multipart/report; report-type=delivery-status;\r\n"
        ' boundary="=_relay-dsn-boundary"\r\n'
        "\r\n"
        "--=_relay-dsn-boundary\r\n"
        "Content-Type: text/plain\r\n"
        "\r\n"
        "The recipient could not be reached.\r\n"
        "--=_relay-dsn-boundary\r\n"
        "Content-Type: message/delivery-status\r\n"
        "\r\n" + delivery_status + "--=_relay-dsn-boundary\r\n"
        "Content-Type: message/rfc822\r\n"
        "\r\n"
        "From: alice@example.com\r\n"
        "To: bob@example.net\r\n"
        "Subject: Hello\r\n"
        "\r\n"
        "Hi\r\n"
        "--=_relay-dsn-boundary--\r\n"
    ).encode()


def make_delayed_dsn_email() -> bytes:
    """Return a raw DSN reporting a temporary delivery delay."""
    return make_dsn_email(
        action="delayed",
        status="4.4.1",
        diagnostic_code="smtp; 421 try again later",
    )


def make_delivered_dsn_email() -> bytes:
    """Return a raw DSN reporting a successful delivery."""
    return make_dsn_email(action="delivered", status="2.0.0", diagnostic_code="")
