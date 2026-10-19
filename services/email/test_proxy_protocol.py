from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aiosmtpd.proxy_protocol import AF, PROTO, V2_CMD, ProxyData
from aiosmtpd.smtp import SMTP

from services.email.proxy_protocol import (
    ProxyProtocolController,
    ProxyProtocolSMTP,
    get_client_ip,
    get_local_ip,
)


def make_proxy_data(src_addr="203.0.113.7", dst_addr="188.245.198.157"):
    """Return a valid PROXY v2 header for a stream connection."""
    proxy_data = ProxyData(version=2)
    proxy_data.command = V2_CMD.PROXY
    proxy_data.family = AF.INET
    proxy_data.protocol = PROTO.STREAM
    proxy_data.src_addr = src_addr
    proxy_data.dst_addr = dst_addr
    return proxy_data


class TestGetClientIp:
    def test_get_client_ip__prefers_proxy_source(self):
        session = SimpleNamespace(
            proxy_data=make_proxy_data(), peer=("10.244.0.1", 1234)
        )
        assert get_client_ip(session) == "203.0.113.7"

    def test_get_client_ip__falls_back_to_peer(self):
        session = SimpleNamespace(peer=("10.244.0.1", 1234))
        assert get_client_ip(session) == "10.244.0.1"


class TestGetLocalIp:
    def test_get_local_ip__prefers_proxy_destination(self):
        session = SimpleNamespace(proxy_data=make_proxy_data())
        assert get_local_ip(session) == "188.245.198.157"

    def test_get_local_ip__falls_back_to_socket_name(self):
        transport = MagicMock()
        transport.get_extra_info.return_value = ("10.244.0.5", 25)
        assert get_local_ip(SimpleNamespace(), transport) == "10.244.0.5"

    def test_get_local_ip__falls_back_when_proxy_destination_is_unset(self):
        proxy_data = ProxyData(version=1)
        proxy_data.family = AF.UNSPEC
        proxy_data.protocol = PROTO.UNSPEC
        transport = MagicMock()
        transport.get_extra_info.return_value = ("10.244.0.5", 25)
        session = SimpleNamespace(proxy_data=proxy_data)
        assert get_local_ip(session, transport) == "10.244.0.5"


class TestProxyProtocolSMTP:
    def test_connection_made__restores_proxy_data_after_starttls(self):
        smtp = object.__new__(ProxyProtocolSMTP)
        proxy_data = make_proxy_data()
        smtp.session = SimpleNamespace(proxy_data=proxy_data)

        def connection_made(self, transport):
            self.session = SimpleNamespace(proxy_data=None)

        with patch.object(SMTP, "connection_made", connection_made):
            smtp.connection_made(MagicMock())

        assert smtp.session.proxy_data is proxy_data


class TestProxyProtocolController:
    def test_factory__creates_proxy_protocol_smtp(self):
        controller = object.__new__(ProxyProtocolController)
        controller.handler = object()
        controller.SMTP_kwargs = {"hostname": "mx.example.com"}
        with patch("services.email.proxy_protocol.ProxyProtocolSMTP") as smtp:
            assert controller.factory() is smtp.return_value
        smtp.assert_called_once_with(controller.handler, hostname="mx.example.com")
