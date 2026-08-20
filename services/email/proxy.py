"""Shared PROXY protocol handling for the mail servers."""


class ProxyProtocolMixin:
    """Accept PROXY protocol headers and update the session peer."""

    async def handle_PROXY(self, server, session, envelope, proxy_data):
        """Update the session peer from the PROXY header.

        The backend trusts the PROXY header because it is reachable only from
        HAProxy on the internal app network. HAProxy is the sole PROXY sender.
        """
        if proxy_data.src_addr:
            session.peer = (str(proxy_data.src_addr), proxy_data.src_port or 0)
        return True
