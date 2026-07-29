from dataclasses import dataclass
from enum import StrEnum


class Alignment(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class AuthResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEUTRAL = "neutral"
    NONE = "none"
    PERMERROR = "permerror"
    TEMPERROR = "temperror"


class Disposition(StrEnum):
    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class DmarcPolicy:
    p: str = "none"
    sp: str = "none"
    adkim: str = "r"
    aspf: str = "r"
    rua: str = ""
    ruf: str = ""
    pct: int = 100

    @classmethod
    def lookup(cls, domain):
        import dns.resolver

        try:
            records = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
        except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
            return cls()
        for record in records:
            text = "".join(
                s.decode() if isinstance(s, bytes) else s for s in record.strings
            )
            if not text.startswith("v=DMARC1"):
                continue
            fields = {}
            for part in text.split(";"):
                part = part.strip()
                if "=" not in part:
                    continue
                key, value = (s.strip() for s in part.split("=", 1))
                if key in {"p", "sp", "adkim", "aspf", "rua", "ruf"}:
                    fields[key] = value
                elif key == "pct":
                    fields[key] = int(value)
            return cls(**fields)
        return cls()

    @property
    def rua_address(self):
        return self._extract_mailto(self.rua)

    @property
    def ruf_address(self):
        return self._extract_mailto(self.ruf)

    def disposition(self, dkim_aligned, spf_aligned):
        if dkim_aligned or spf_aligned:
            return Disposition.NONE
        return self.p

    @staticmethod
    def _extract_mailto(value):
        if not value:
            return ""
        for part in value.split(","):
            part = part.strip()
            if part.startswith("mailto:"):
                return part.removeprefix("mailto:").strip()
        return ""


@dataclass(frozen=True, slots=True)
class DmarcEvaluation:
    source_ip_address: str | None
    header_from: str
    envelope_from: str
    dkim_domain: str
    dkim_result: AuthResult
    dkim_alignment: Alignment
    spf_domain: str
    spf_result: AuthResult
    spf_alignment: Alignment
    disposition: Disposition

    @classmethod
    def from_message(cls, incoming_message):
        """Return DMARC evaluation results for an incoming message."""
        from .evaluation import (
            check_alignment,
            check_spf,
            extract_domain,
            extract_source_ip,
            verify_dkim,
        )

        raw_bytes = incoming_message.raw_body.read()
        from email import message_from_bytes

        msg = message_from_bytes(raw_bytes)
        header_from_domain = extract_domain(msg.get("From", ""))
        envelope_from_domain = extract_domain(incoming_message.mail_from)
        source_ip = extract_source_ip(msg)
        dmarc_policy = DmarcPolicy.lookup(header_from_domain)
        dkim_result, dkim_domain = verify_dkim(raw_bytes)
        spf_result, spf_domain = check_spf(source_ip, envelope_from_domain)
        dkim_aligned = check_alignment(
            dkim_domain, header_from_domain, dmarc_policy.adkim
        )
        spf_aligned = check_alignment(spf_domain, header_from_domain, dmarc_policy.aspf)

        return cls(
            source_ip_address=source_ip,
            header_from=header_from_domain,
            envelope_from=envelope_from_domain,
            dkim_domain=dkim_domain,
            dkim_result=dkim_result,
            dkim_alignment=Alignment.PASS if dkim_aligned else Alignment.FAIL,
            spf_domain=spf_domain,
            spf_result=spf_result,
            spf_alignment=Alignment.PASS if spf_aligned else Alignment.FAIL,
            disposition=dmarc_policy.disposition(dkim_aligned, spf_aligned),
        )
