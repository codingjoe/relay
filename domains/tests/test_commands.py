import signal
from io import StringIO
from unittest.mock import call, create_autospec, patch

import pytest
from django.core.management import call_command
from dnslib.server import DNSServer


class TestDnsCommand:
    def test_handle__starts_and_stops_udp_and_tcp(self):
        udp_server = create_autospec(DNSServer, instance=True)
        tcp_server = create_autospec(DNSServer, instance=True)
        signal_handlers = {}

        def register_signal_handler(signal_number, handler):
            signal_handlers[signal_number] = handler

        def send_termination_signal(seconds):
            signal_handlers[signal.SIGTERM](signal.SIGTERM, None)

        with (
            patch(
                "domains.management.commands.dns.DNSServer",
                side_effect=(udp_server, tcp_server),
            ) as server_class,
            patch("domains.management.commands.dns.DNSReplyResolver") as resolver_class,
            patch("domains.management.commands.dns.DNSLogger") as logger_class,
            patch(
                "domains.management.commands.dns.signal.signal",
                side_effect=register_signal_handler,
            ),
            patch(
                "domains.management.commands.dns.time.sleep",
                side_effect=send_termination_signal,
            ),
            pytest.raises(SystemExit) as error,
        ):
            call_command(
                "dns",
                "--host",
                "127.0.0.1",
                "--port",
                "5353",
                stdout=StringIO(),
            )

        resolver = resolver_class.return_value
        logger = logger_class.return_value
        resolver_class.assert_called_once_with()
        logger_class.assert_called_once_with(log="-request,-reply,-truncated,-error")
        assert server_class.call_args_list == [
            call(resolver, address="127.0.0.1", port=5353, logger=logger),
            call(
                resolver,
                address="127.0.0.1",
                port=5353,
                tcp=True,
                logger=logger,
            ),
        ]
        udp_server.start_thread.assert_called_once_with()
        tcp_server.start_thread.assert_called_once_with()
        udp_server.stop.assert_called_once_with()
        tcp_server.stop.assert_called_once_with()
        assert error.value.code == 0
