"""PROXY protocol support for SMTP servers behind the Caddy L4 balancer."""

import datetime

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Session


class ProxyProtocolMixin:
    """Accept sessions whose connection starts with a valid PROXY protocol header."""

    async def handle_PROXY(self, server, session, envelope, proxy_data):
        """Accept the session when the PROXY protocol header is valid."""
        return proxy_data.valid


class ProxyProtocolSMTP(SMTP):
    """Keep the PROXY protocol data across the STARTTLS session reset."""

    def connection_made(self, transport):
        proxy_data = self.session.proxy_data if self.session else None
        super().connection_made(transport)
        if proxy_data is not None:
            self.session.proxy_data = proxy_data


class ProxyProtocolController(Controller):
    """Create SMTP connections that keep the PROXY protocol data across STARTTLS."""

    def factory(self):
        return ProxyProtocolSMTP(self.handler, **self.SMTP_kwargs)


def get_client_ip(session: Session) -> str:
    """Return the client IPv4 or IPv6 address, preferring the PROXY protocol header."""
    proxy_data = getattr(session, "proxy_data", None)
    if proxy_data and proxy_data.src_addr:
        return str(proxy_data.src_addr)
    return session.peer[0] if session.peer else ""


def get_local_ip(session: Session, transport=None) -> str:
    """Return the local IPv4 or IPv6 address that accepted the connection."""
    proxy_data = getattr(session, "proxy_data", None)
    sockname = transport.get_extra_info("sockname") if transport else None
    if proxy_data and proxy_data.dst_addr:
        local_ip = str(proxy_data.dst_addr)
    else:
        local_ip = sockname[0] if sockname else ""
    return local_ip


def proxy_protocol_timeout_seconds(timeout: datetime.timedelta | None) -> float | None:
    """Convert the PROXY protocol timeout to the seconds aiosmtpd expects."""
    return timeout.total_seconds() if timeout else None
