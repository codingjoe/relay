from io import StringIO
from unittest.mock import patch


def test_msa_command__parses_host_and_ports():
    with patch(
        "services.email.msa.management.commands.msa.run_smtp_server"
    ) as mock_run:
        mock_run.side_effect = SystemExit(0)
        from django.core.management import call_command

        try:
            call_command(
                "msa", "--host", "127.0.0.1", "--ports", "587", stdout=StringIO()
            )
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("host") == "127.0.0.1"
        assert call_kwargs.kwargs.get("ports") == [587]
