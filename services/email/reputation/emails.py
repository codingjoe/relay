"""Outgoing email payloads for reputation reports."""

from email import message_from_bytes
from email.message import MIMEPart

from django.conf import settings
from django.core.mail import EmailMessage


def send_fbl_report(message):
    """Deliver an ARF complaint report to the platform-wide FBL
    reporting address.

    FBL agreements exist between mailbox providers, not individual
    sender domains. Relay sends one ARF complaint per detected spam
    message to the platform-wide FBL reporting address configured
    with `RELAY_FBL_REPORTING_ADDRESS`. Does nothing when no address
    is configured.
    """
    match address := settings.RELAY_FBL_REPORTING_ADDRESS:
        case None | "":
            return

    raw_headers = ""
    if message.raw_body:
        parsed = message_from_bytes(message.raw_body.read())
        raw_headers = (
            "".join(f"{k}: {v}\r\n" for k, v in parsed.items())
            .encode("ascii", "backslashreplace")
            .decode("ascii")[:2000]
        )

    sender_domain = message.mail_from.rsplit("@", 1)[-1]
    feedback_part = MIMEPart()
    feedback_part["Content-Type"] = "message/feedback-report"
    feedback_part.set_payload(
        "".join(
            f"{key}: {value}\r\n"
            for key, value in {
                "Feedback-Type": "abuse",
                "User-Agent": "relay",
                "Version": "1",
                "Arrival-Date": message.created_at.isoformat(),
                "Original-Mail-From": message.mail_from,
                "Original-Rcpt-To": message.rcpt_to.split(",")[0],
                "Source-IP": getattr(message, "source_ip_address", "") or "",
                "Delivery-Result": "spam",
            }.items()
            if value
        )
    )
    headers_part = MIMEPart()
    headers_part["Content-Type"] = "text/rfc822-headers"
    headers_part.set_payload(raw_headers)
    email = MultipartReportEmail(
        subject=f"FBL report for {sender_domain}",
        body="Feedback loop complaint report.",
        from_email=f"{settings.RELAY_FBL_LOCAL_PART}@{settings.RELAY_PLATFORM_DOMAIN}",
        to=[address],
    )
    email.attach(feedback_part)
    email.attach(headers_part)
    email.send()


class MultipartReportEmail(EmailMessage):
    """Serialize the MIME payload as `multipart/report;
    report-type=feedback-loop`."""

    def message(self):
        msg = super().message()
        msg.replace_header(
            "Content-Type",
            str(msg["Content-Type"]).replace(
                "multipart/mixed", "multipart/report; report-type=feedback-loop"
            ),
        )
        return msg
