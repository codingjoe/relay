"""Authoritative DNS server."""

import socket
import threading

from django.db import DatabaseError
from dnslib import DNSRecord
from dnslib.dns import RCODE, DNSError

from .resolver import DNSResolver


class DNSServer:
    """Serve authoritative DNS records."""

    def __init__(self, host="0.0.0.0", port=53):
        self.host = host
        self.port = port
        self.resolver = DNSResolver()
        self._running = False
        self._socks = []

    def handle_request(self, data, addr, sock):
        """Handle a single DNS request."""
        try:
            request = DNSRecord.parse(data)
        except DNSError:
            pass
        else:
            reply = request.reply()
            reply.header.rcode = RCODE.NOERROR

            try:
                records = self.resolver.resolve(request.q.qname, request.q.qtype)
                for rr in records:
                    reply.add_answer(rr)
            except DNSError, DatabaseError:
                reply.header.rcode = RCODE.SERVFAIL

            try:
                sock.sendto(reply.pack(), addr)
            except OSError:
                pass

    def run_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        self._socks.append(sock)

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                threading.Thread(
                    target=self.handle_request,
                    args=(data, addr, sock),
                    daemon=True,
                ).start()
            except OSError:
                break

    def run_tcp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)
        self._socks.append(sock)

        while self._running:
            try:
                conn, _addr = sock.accept()
                threading.Thread(
                    target=self.handle_tcp_request,
                    args=(conn,),
                    daemon=True,
                ).start()
            except OSError:
                break

    def handle_tcp_request(self, conn):
        try:
            data = conn.recv(2)
            if len(data) >= 2:
                length = int.from_bytes(data, "big")
                data = conn.recv(length)
                self.handle_tcp_query(data, conn)
        except OSError:
            pass
        finally:
            conn.close()

    def handle_tcp_query(self, data, conn):
        try:
            request = DNSRecord.parse(data)
        except DNSError:
            pass
        else:
            qname = request.q.qname
            qtype = request.q.qtype

            reply = request.reply()
            reply.header.rcode = RCODE.NOERROR

            try:
                records = self.resolver.resolve(qname, qtype)
                for rr in records:
                    reply.add_answer(rr)
            except DNSError, DatabaseError:
                reply.header.rcode = RCODE.SERVFAIL

            packed = reply.pack()
            conn.sendall(len(packed).to_bytes(2, "big") + packed)

    def start(self):
        self._running = True
        udp_thread = threading.Thread(target=self.run_udp, daemon=True)
        tcp_thread = threading.Thread(target=self.run_tcp, daemon=True)
        udp_thread.start()
        tcp_thread.start()
        return udp_thread, tcp_thread

    def stop(self):
        self._running = False
        for sock in self._socks:
            try:
                sock.close()
            except OSError:
                pass
