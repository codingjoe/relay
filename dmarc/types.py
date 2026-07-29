from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DmarcPolicy:
    """Parsed DMARC TXT record for a domain."""

    p: str = "none"
    sp: str = "none"
    adkim: str = "r"
    aspf: str = "r"
    rua: str = ""
    ruf: str = ""
    pct: int = 100

    @classmethod
    def lookup(cls, domain):
        """Return the DMARC TXT record parsed from DNS for a domain."""
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
        """Return the first mailto: address from the rua tag."""
        return self._extract_mailto(self.rua)

    @property
    def ruf_address(self):
        """Return the first mailto: address from the ruf tag."""
        return self._extract_mailto(self.ruf)

    def disposition(self, dkim_aligned, spf_aligned):
        """Return the DMARC disposition based on alignment results."""
        if dkim_aligned or spf_aligned:
            return "none"
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
    """DMARC evaluation result for a single incoming message."""

    source_ip_address: str | None
    header_from: str
    envelope_from: str
    dkim_domain: str
    dkim_result: str
    dkim_alignment: str
    spf_domain: str
    spf_result: str
    spf_alignment: str
    disposition: str
