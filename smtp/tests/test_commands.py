from io import StringIO
from unittest.mock import patch


def test_smtp_command__parses_host_and_port():
    with patch("smtp.management.commands.smtp.run_smtp_server") as mock_run:
        mock_run.side_effect = SystemExit(0)
        from django.core.management import call_command

        try:
            call_command(
                "smtp", "--host", "127.0.0.1", "--port", "587", stdout=StringIO()
            )
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("host") == "127.0.0.1"
        assert call_kwargs.kwargs.get("port") == 587
