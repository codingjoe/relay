import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpcore
import httpx


class UnsafeNetworkOperation(OSError):
    """Indicate that a network destination or response is unsafe."""


def resolve_global_addresses(hostname, port):
    """Return stream addresses only when every resolution result is global."""
    try:
        address_info = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise UnsafeNetworkOperation(f"Could not resolve {hostname}") from error

    resolved_addresses = []
    seen_addresses = set()
    for family, socket_type, protocol, _canonical_name, socket_address in address_info:
        address = ipaddress.ip_address(socket_address[0])
        if not address.is_global:
            raise UnsafeNetworkOperation(
                f"Network destination {hostname} resolved to a non-global address"
            )
        key = family, socket_address
        if key not in seen_addresses:
            seen_addresses.add(key)
            resolved_addresses.append((family, socket_type, protocol, socket_address))

    if not resolved_addresses:
        raise UnsafeNetworkOperation(f"Could not resolve {hostname}")
    return resolved_addresses


def validate_global_url(url):
    """Validate that an HTTPS URL resolves only to global addresses."""
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise UnsafeNetworkOperation("Network destination must be an HTTPS URL")
    try:
        port = parsed_url.port or 443
    except ValueError as error:
        raise UnsafeNetworkOperation(
            "Network destination has an invalid port"
        ) from error
    resolve_global_addresses(parsed_url.hostname, port)


async def connect_global_tcp_socket(hostname, port, timeout):
    """Connect to a prevalidated global address and return its socket."""
    loop = asyncio.get_running_loop()
    last_error = None
    for family, socket_type, protocol, socket_address in resolve_global_addresses(
        hostname, port
    ):
        sock = socket.socket(family, socket_type, protocol)
        sock.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(sock, socket_address), timeout)
        except (OSError, TimeoutError) as error:
            last_error = error
            sock.close()
            continue
        return sock
    raise UnsafeNetworkOperation(f"Could not connect to {hostname}") from last_error


def read_bounded_response_text(response, maximum_bytes):
    """Read an identity-encoded HTTP response up to a byte limit."""
    content_encoding = response.headers.get("Content-Encoding", "identity").lower()
    if content_encoding != "identity":
        raise UnsafeNetworkOperation("Compressed HTTP responses are not accepted")

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > maximum_bytes:
                raise UnsafeNetworkOperation("HTTP response is too large")
        except ValueError as error:
            raise UnsafeNetworkOperation(
                "HTTP response has an invalid length"
            ) from error

    body = bytearray()
    for chunk in response.iter_raw():
        if len(body) + len(chunk) > maximum_bytes:
            raise UnsafeNetworkOperation("HTTP response is too large")
        body.extend(chunk)
    encoding = response.encoding or "utf-8"
    return bytes(body).decode(encoding, errors="replace")


class GlobalNetworkBackend(httpcore.SyncBackend):
    """Dial only a vetted address while retaining the original TLS hostname."""

    def connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        deadline = time.monotonic() + timeout if timeout is not None else None
        last_error = None
        for (
            _family,
            _socket_type,
            _protocol,
            socket_address,
        ) in resolve_global_addresses(host, port):
            try:
                stream = super().connect_tcp(
                    socket_address[0],
                    port,
                    timeout=timeout_before_deadline(
                        deadline,
                        maximum_timeout=timeout,
                    ),
                    local_address=local_address,
                    socket_options=socket_options,
                )
                return DeadlineNetworkStream(stream, deadline)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
        raise httpcore.ConnectError(f"Could not connect to {host}") from last_error


def timeout_before_deadline(
    deadline,
    timeout_error=httpcore.ConnectTimeout,
    maximum_timeout=None,
):
    """Return seconds remaining before a monotonic deadline."""
    if deadline is None:
        return maximum_timeout
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise timeout_error("Network operation exceeded its deadline")
    return min(timeout, maximum_timeout) if maximum_timeout is not None else timeout


class DeadlineNetworkStream(httpcore.NetworkStream):
    """Apply one monotonic deadline across all operations on a connection."""

    def __init__(self, stream, deadline):
        self.stream = stream
        self.deadline = deadline

    def read(self, max_bytes, timeout=None):
        return self.stream.read(
            max_bytes,
            timeout=timeout_before_deadline(
                self.deadline,
                httpcore.ReadTimeout,
                timeout,
            ),
        )

    def write(self, buffer, timeout=None):
        return self.stream.write(
            buffer,
            timeout=timeout_before_deadline(
                self.deadline,
                httpcore.WriteTimeout,
                timeout,
            ),
        )

    def close(self):
        return self.stream.close()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = self.stream.start_tls(
            ssl_context,
            server_hostname=server_hostname,
            timeout=timeout_before_deadline(
                self.deadline,
                httpcore.ConnectTimeout,
                timeout,
            ),
        )
        return DeadlineNetworkStream(stream, self.deadline)

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


def global_http_client():
    """Return an HTTP client configured for bounded public egress."""
    transport = httpx.HTTPTransport(trust_env=False)
    transport._pool.close()
    transport._pool = httpcore.ConnectionPool(network_backend=GlobalNetworkBackend())
    return httpx.Client(
        follow_redirects=False,
        headers={"Accept-Encoding": "identity"},
        transport=transport,
        trust_env=False,
    )
