from unittest.mock import MagicMock, patch

import pytest


class TestSmtpServerInit:
    def test_init__defaults(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        assert server.host == "0.0.0.0"
        assert server.ports == (587, 465)
        assert server.implicit_tls_ports == (465,)
        assert server.controllers == []

    def test_init__custom(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer(host="127.0.0.1", ports=(587,))
        assert server.host == "127.0.0.1"
        assert server.ports == (587,)


class TestSmtpServerLifecycle:
    @patch("services.email.smtp.server.build_tls_context")
    @patch("services.email.smtp.server.Controller")
    def test_start__creates_controller(self, mock_controller_cls, mock_build_tls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        mock_build_tls.return_value = MagicMock()
        server = SMTPServer()
        server.start()
        assert server.controllers == [mock_controller, mock_controller]
        assert mock_controller.start.call_count == 2

    @patch("services.email.smtp.server.build_tls_context")
    @patch("services.email.smtp.server.Controller")
    def test_stop__calls_controller_stop(self, mock_controller_cls, mock_build_tls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        mock_build_tls.return_value = MagicMock()
        server = SMTPServer()
        server.start()
        server.stop()
        assert mock_controller.stop.call_count == 2

    def test_stop__without_start(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        server.stop()
        assert server.controllers == []

    def test_start__raises_when_implicit_tls_without_cert(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        with pytest.raises(ValueError, match="Implicit TLS ports require"):
            server.start()

    @patch("services.email.smtp.server.build_tls_context")
    @patch("services.email.smtp.server.Controller")
    def test_start__does_not_raise_when_no_implicit_tls_ports(
        self, mock_controller_cls, mock_build_tls
    ):
        from services.email.smtp.server import SMTPServer

        mock_build_tls.return_value = None
        server = SMTPServer(ports=(587,), implicit_tls_ports=())
        server.start()
        assert len(server.controllers) == 1
