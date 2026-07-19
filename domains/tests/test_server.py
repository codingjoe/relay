from unittest.mock import MagicMock, patch

import dnslib
import pytest
from dnslib import DNSLabel, QTYPE


class TestDnsServerInit:
    def test_init__defaults(self):
        from domains.server import DNSServer

        server = DNSServer()
        assert server.host == "0.0.0.0"
        assert server.port == 53
        assert server._running is False
        assert server._socks == []

    def test_init__custom(self):
        from domains.server import DNSServer

        server = DNSServer(host="127.0.0.1", port=5353)
        assert server.host == "127.0.0.1"
        assert server.port == 5353


@pytest.mark.django_db
class TestHandleRequest:
    def test_handle_request__unknown_domain(self):
        from domains.server import DNSServer

        server = DNSServer()
        request = dnslib.DNSRecord(
            q=dnslib.DNSQuestion(DNSLabel("unknown.com"), QTYPE.A)
        )
        sock = MagicMock()
        server.handle_request(request.pack(), ("127.0.0.1", 12345), sock)
        sock.sendto.assert_called_once()
        reply = dnslib.DNSRecord.parse(sock.sendto.call_args[0][0])
        assert reply.header.rcode == dnslib.RCODE.NOERROR
        assert len(reply.rr) == 0

    def test_handle_request__known_domain(self):
        from domains.models import Domain
        from domains.server import DNSServer

        Domain.objects.create(name="open.localhost", org=None)
        server = DNSServer()
        request = dnslib.DNSRecord(
            q=dnslib.DNSQuestion(DNSLabel("open.localhost"), QTYPE.A)
        )
        sock = MagicMock()
        server.handle_request(request.pack(), ("127.0.0.1", 12345), sock)
        sock.sendto.assert_called_once()
        reply = dnslib.DNSRecord.parse(sock.sendto.call_args[0][0])
        assert reply.header.rcode == dnslib.RCODE.NOERROR
        assert len(reply.rr) >= 1

    def test_handle_request__invalid_data(self):
        from domains.server import DNSServer

        server = DNSServer()
        sock = MagicMock()
        server.handle_request(b"invalid", ("127.0.0.1", 12345), sock)
        sock.sendto.assert_not_called()


@pytest.mark.django_db
class TestDnsServerLifecycle:
    def test_start_stop__running_flag(self):
        from domains.server import DNSServer

        server = DNSServer(host="127.0.0.1", port=0)
        with patch.object(server, "run_udp"), patch.object(server, "run_tcp"):
            server.start()
            assert server._running is True
            server.stop()
            assert server._running is False


@pytest.mark.django_db
class TestHandleTcpQuery:
    def test_handle_tcp_query__known_domain(self):
        from domains.models import Domain
        from domains.server import DNSServer

        Domain.objects.create(name="open.localhost", org=None)
        server = DNSServer()
        request = dnslib.DNSRecord(
            q=dnslib.DNSQuestion(DNSLabel("open.localhost"), QTYPE.A)
        )
        conn = MagicMock()
        server.handle_tcp_query(request.pack(), conn)
        conn.sendall.assert_called_once()
        sent = conn.sendall.call_args[0][0]
        length = int.from_bytes(sent[:2], "big")
        assert length > 0
        reply = dnslib.DNSRecord.parse(sent[2:])
        assert reply.header.rcode == dnslib.RCODE.NOERROR
        assert len(reply.rr) >= 1
