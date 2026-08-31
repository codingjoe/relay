"""PROXY protocol support for SMTP servers behind the Caddy L4 balancer."""

from aiosmtpd.smtp import Session


class ProxyProtocolMixin:
    """Accept sessions whose connection starts with a valid PROXY protocol header."""

    async def handle_PROXY(self, server, session, envelope, proxy_data):
        """Accept the session when the PROXY protocol header is valid."""
        return proxy_data.valid


def get_client_ip(session: Session) -> str:
    """Return the client IPv4 or IPv6 address, preferring the PROXY protocol header."""
    proxy_data = getattr(session, "proxy_data", None)
    if proxy_data and proxy_data.src_addr:
        return str(proxy_data.src_addr)
    return session.peer[0] if session.peer else ""
