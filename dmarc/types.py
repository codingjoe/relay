import ipaddress
import re
from dataclasses import dataclass
from email import message_from_bytes
from enum import StrEnum

import dkim
import dns.resolver

RECEIVED_IP_PATTERN = re.compile(r"\[(\d+\.\d+\.\d+\.\d+)\]|\[([0-9a-fA-F:]+)\]")
EMAIL_DOMAIN_PATTERN = re.compile(r"@([\w.-]+)")


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
        return self.extract_mailto(self.rua)

    @property
    def ruf_address(self):
        return self.extract_mailto(self.ruf)

    def disposition(self, dkim_aligned, spf_aligned):
        if dkim_aligned or spf_aligned:
            return Disposition.NONE
        return self.p

    @staticmethod
    def extract_mailto(value):
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
        raw_bytes = incoming_message.raw_body.read()
        msg = message_from_bytes(raw_bytes)
        header_from_domain = cls.extract_domain(msg.get("From", ""))
        envelope_from_domain = cls.extract_domain(incoming_message.mail_from)
        source_ip = cls.extract_source_ip(msg)
        policy = DmarcPolicy.lookup(header_from_domain)
        dkim_result, dkim_domain = cls.verify_dkim(raw_bytes)
        spf_result, spf_domain = cls.check_spf(source_ip, envelope_from_domain)
        dkim_aligned = cls.check_alignment(
            dkim_domain, header_from_domain, policy.adkim
        )
        spf_aligned = cls.check_alignment(spf_domain, header_from_domain, policy.aspf)

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
            disposition=policy.disposition(dkim_aligned, spf_aligned),
        )

    @staticmethod
    def extract_domain(email_or_header):
        if match := EMAIL_DOMAIN_PATTERN.search(email_or_header):
            return match.group(1).lower()
        return email_or_header.lower().strip()

    @staticmethod
    def extract_source_ip(msg):
        for header in msg.get_all("Received", []):
            if match := RECEIVED_IP_PATTERN.search(header):
                ip_str = match.group(1) or match.group(2)
                try:
                    ipaddress.ip_address(ip_str)
                    return ip_str
                except ValueError:
                    continue
        return None

    @staticmethod
    def verify_dkim(raw_bytes):
        try:
            verified = dkim.verify(raw_bytes)
        except dkim.DKIMException:
            return AuthResult.PERMERROR, ""
        if verified:
            msg = message_from_bytes(raw_bytes)
            for key, value in msg.items():
                if key.lower() == "dkim-signature":
                    params = dict(
                        s.strip().split("=", 1)
                        for s in value.split(";")
                        if "=" in s.strip()
                    )
                    return AuthResult.PASS, params.get("d", "")
            return AuthResult.PASS, ""
        return AuthResult.FAIL, ""

    @staticmethod
    def check_spf(source_ip, domain):
        if source_ip and domain:
            try:
                records = dns.resolver.resolve(domain, "TXT")
            except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
                return AuthResult.NONE, domain
            for record in records:
                text = "".join(
                    s.decode() if isinstance(s, bytes) else s for s in record.strings
                )
                if not text.startswith("v=spf1"):
                    continue
                if "a" in text or "mx" in text or f"ip4:{source_ip}" in text:
                    return AuthResult.PASS, domain
                if "~all" in text or "-all" in text:
                    return AuthResult.FAIL, domain
                if "+all" in text or "?all" in text:
                    return AuthResult.NEUTRAL, domain
                return AuthResult.NEUTRAL, domain
            return AuthResult.NONE, domain
        return AuthResult.NONE, domain

    @staticmethod
    def check_alignment(auth_domain, header_from_domain, policy):
        if auth_domain and header_from_domain:
            mode = policy if isinstance(policy, str) else "r"
            auth = auth_domain.lower()
            header = header_from_domain.lower()
            match mode:
                case "s":
                    return auth == header
                case _:
                    return (
                        auth == header
                        or auth.endswith(f".{header}")
                        or header.endswith(f".{auth}")
                    )
        return False
