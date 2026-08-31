import ipaddress
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from email import message_from_bytes
from enum import StrEnum

import dkim
import dns.resolver

logger = logging.getLogger(__name__)

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
    is_published: bool = False
    temperror: bool = False

    @classmethod
    def lookup(cls, domain):
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 2.0
            records = resolver.resolve(f"_dmarc.{domain}", "TXT")
        except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer:
            return cls()
        except dns.exception.Timeout, dns.resolver.NoNameservers:
            logger.warning("DMARC DNS lookup failed for %r", domain, exc_info=True)
            return cls(temperror=True)
        for record in records:
            text = "".join(
                s.decode() if isinstance(s, bytes) else s for s in record.strings
            )
            if text.startswith("v=DMARC1"):
                fields = {}
                for part in text.split(";"):
                    part = part.strip()
                    if "=" in part:
                        key, value = (s.strip() for s in part.split("=", 1))
                        if key in {"p", "sp", "adkim", "aspf", "rua", "ruf"}:
                            fields[key] = value
                        elif key == "pct":
                            with suppress(ValueError):
                                fields[key] = int(value)
                return cls(**fields, is_published=True)
        return cls()

    @property
    def rua_address(self):
        return self.extract_mailto(self.rua)

    @property
    def ruf_address(self):
        return self.extract_mailto(self.ruf)

    def disposition(self, dkim_authenticated: bool, spf_authenticated: bool):
        """Return the policy disposition for mechanisms that passed and aligned."""
        if dkim_authenticated or spf_authenticated:
            return Disposition.NONE
        match self.p:
            case Disposition.QUARANTINE:
                return Disposition.QUARANTINE
            case Disposition.REJECT:
                return Disposition.REJECT
            case _:
                return Disposition.NONE

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
    dmarc_policy_is_published: bool = False
    dmarc_policy_temperror: bool = False

    @property
    def dmarc_authenticated(self) -> bool:
        """Return whether DMARC passed: a mechanism passed and is aligned (RFC 7489 §6.6.2)."""
        return self.is_authenticated(
            self.dkim_result, self.dkim_alignment
        ) or self.is_authenticated(self.spf_result, self.spf_alignment)

    @staticmethod
    def is_authenticated(result: AuthResult, alignment: Alignment) -> bool:
        """Return whether an authentication mechanism passed and is aligned."""
        return result is AuthResult.PASS and alignment is Alignment.PASS

    @classmethod
    def from_message(cls, incoming_message):
        """Return DMARC evaluation results for an incoming message."""
        return cls.from_bytes(
            incoming_message.raw_body.read(),
            incoming_message.mail_from,
        )

    @classmethod
    def from_bytes(cls, raw_bytes, mail_from, client_ip: str = ""):
        """Evaluate DMARC for a message from raw bytes.

        SPF is evaluated against client_ip, the SMTP session's connecting
        address, so forged Received headers cannot authenticate a sender.
        Callers without a session address fall back to the Received headers.
        """
        msg = message_from_bytes(raw_bytes)
        header_from_domain = cls.extract_domain(msg.get("From", ""))
        envelope_from_domain = cls.extract_domain(mail_from)
        source_ip = client_ip or cls.extract_source_ip(msg)
        policy = DmarcPolicy.lookup(header_from_domain)
        dkim_result, dkim_domain = cls.verify_dkim(raw_bytes)
        spf_result, spf_domain = cls.check_spf(source_ip, envelope_from_domain)
        dkim_alignment = (
            Alignment.PASS
            if cls.check_alignment(dkim_domain, header_from_domain, policy.adkim)
            else Alignment.FAIL
        )
        spf_alignment = (
            Alignment.PASS
            if cls.check_alignment(spf_domain, header_from_domain, policy.aspf)
            else Alignment.FAIL
        )
        return cls(
            source_ip_address=source_ip,
            header_from=header_from_domain,
            envelope_from=envelope_from_domain,
            dkim_domain=dkim_domain,
            dkim_result=dkim_result,
            dkim_alignment=dkim_alignment,
            spf_domain=spf_domain,
            spf_result=spf_result,
            spf_alignment=spf_alignment,
            disposition=policy.disposition(
                cls.is_authenticated(dkim_result, dkim_alignment),
                cls.is_authenticated(spf_result, spf_alignment),
            ),
            dmarc_policy_is_published=policy.is_published,
            dmarc_policy_temperror=policy.temperror,
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
                    pass
        return None

    @staticmethod
    def verify_dkim(raw_bytes):
        try:
            verified = dkim.verify(raw_bytes)
        except dkim.DKIMException, IndexError:
            logger.warning("DKIM verification failed", exc_info=True)
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
                resolver = dns.resolver.Resolver()
                resolver.lifetime = 2.0
                records = resolver.resolve(domain, "TXT")
            except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer:
                return AuthResult.NONE, domain
            except dns.exception.Timeout, dns.resolver.NoNameservers:
                logger.warning("SPF DNS lookup failed for %r", domain, exc_info=True)
                return AuthResult.TEMPERROR, domain
            for record in records:
                text = "".join(
                    s.decode() if isinstance(s, bytes) else s for s in record.strings
                )
                if text.startswith("v=spf1"):
                    mechanisms = text.split()
                    for mech in mechanisms:
                        if mech == "a" or mech == "mx" or mech == f"ip4:{source_ip}":
                            return AuthResult.PASS, domain
                        if mech in ("~all", "-all"):
                            return AuthResult.FAIL, domain
                        if mech in ("+all", "?all"):
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
