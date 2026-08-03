from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command


class TestDnsCommand:
    def test_dns_command__parses_host_and_port(self):
        with (
            patch("domains.management.commands.dns.DNSServer") as mock_server_cls,
            patch("domains.management.commands.dns.signal") as mock_signal,
        ):
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server
            mock_signal.signal.side_effect = SystemExit(0)
            try:
                call_command(
                    "dns", "--host", "127.0.0.1", "--port", "5353", stdout=StringIO()
                )
            except SystemExit:
                pass

            mock_server_cls.assert_called_once_with(host="127.0.0.1", port=5353)
            mock_server.start.assert_called_once()
