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
