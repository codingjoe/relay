"""Bounded dnslib server adapters."""

import socket
import socketserver
import struct
import threading
import time

from django.db import close_old_connections
from dnslib.dns import DNSError
from dnslib.server import DNSHandler
from dnslib.server import DNSServer as LibraryDNSServer


def receive_exactly(connection, byte_count, deadline):
    """Receive an exact byte count before the deadline."""
    chunks = []
    remaining_byte_count = byte_count
    while remaining_byte_count:
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            raise TimeoutError("DNS TCP request exceeded its deadline.")
        connection.settimeout(min(remaining_time, BoundedDNSHandler.TCP_READ_TIMEOUT))
        chunk = connection.recv(remaining_byte_count)
        if not chunk:
            raise ConnectionError("DNS TCP connection closed before the frame ended.")
        chunks.append(chunk)
        remaining_byte_count -= len(chunk)
    return b"".join(chunks)


class BoundedDNSHandler(DNSHandler):
    """Handle one DNS request with bounded TCP reads and ORM cleanup."""

    MAX_TCP_REQUEST_SIZE = 4096
    TCP_READ_TIMEOUT = 2
    TCP_REQUEST_TIMEOUT = 5

    def handle(self):
        close_old_connections()
        try:
            if self.server.socket_type == socket.SOCK_STREAM:
                self.handle_tcp()
            else:
                self.handle_udp()
        finally:
            close_old_connections()

    def handle_tcp(self):
        """Read and answer one length-prefixed TCP request."""
        self.protocol = "tcp"
        deadline = time.monotonic() + self.TCP_REQUEST_TIMEOUT
        try:
            request_size = struct.unpack(
                "!H", receive_exactly(self.request, 2, deadline)
            )[0]
            if not 0 < request_size <= self.MAX_TCP_REQUEST_SIZE:
                raise ConnectionError("DNS TCP frame has an invalid size.")
            data = receive_exactly(self.request, request_size, deadline)
            self.answer(data, deadline)
        except OSError as error:
            self.server.logger.log_error(self, error)

    def handle_udp(self):
        """Answer one UDP request."""
        self.protocol = "udp"
        data, self.connection = self.request
        self.answer(data)

    def answer(self, data, deadline=None):
        """Resolve and send one DNS request using dnslib."""
        self.server.logger.log_recv(self, data)
        try:
            response = self.get_reply(data)
            self.server.logger.log_send(self, response)
            if self.protocol == "tcp":
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    raise TimeoutError("DNS TCP request exceeded its deadline.")
                self.request.settimeout(min(remaining_time, self.TCP_READ_TIMEOUT))
                self.request.sendall(struct.pack("!H", len(response)) + response)
            else:
                self.connection.sendto(response, self.client_address)
        except DNSError as error:
            self.server.logger.log_error(self, error)


class BoundedServerMixin(socketserver.ThreadingMixIn):
    """Reject work when the server's request capacity is full."""

    REQUEST_CAPACITY = 8
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, handler):
        self.request_capacity = threading.BoundedSemaphore(self.REQUEST_CAPACITY)
        if server_address[0] and ":" in server_address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(server_address, handler)

    def process_request(self, request, client_address):
        """Start a request only when capacity is available."""
        if not self.request_capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_capacity.release()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, client_address):
        """Release reserved capacity when request processing finishes."""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_capacity.release()


class BoundedUDPServer(BoundedServerMixin, socketserver.UDPServer):
    """Serve a bounded number of concurrent UDP requests."""

    REQUEST_CAPACITY = 24
    allow_reuse_address = True


class BoundedTCPServer(BoundedServerMixin, socketserver.TCPServer):
    """Serve a bounded number of concurrent TCP requests."""

    REQUEST_CAPACITY = 8
    allow_reuse_address = True


class DNSServer(LibraryDNSServer):
    """Configure dnslib with bounded request handling."""

    def __init__(
        self,
        resolver,
        address="",
        port=53,
        tcp=False,
        logger=None,
        handler=BoundedDNSHandler,
        server=None,
    ):
        if server is None:
            server = BoundedTCPServer if tcp else BoundedUDPServer
        super().__init__(
            resolver,
            address=address,
            port=port,
            tcp=tcp,
            logger=logger,
            handler=handler,
            server=server,
        )

    def stop(self):
        """Stop accepting work and close the listener."""
        self.server.shutdown()
        self.server.server_close()
