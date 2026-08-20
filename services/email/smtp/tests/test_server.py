from unittest.mock import MagicMock, patch


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
    @patch("services.email.smtp.server.Controller")
    def test_start__creates_controller(self, mock_controller_cls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        server = SMTPServer()
        server.start()
        assert server.controllers == [mock_controller, mock_controller]
        assert mock_controller.start.call_count == 2

    @patch("services.email.smtp.server.Controller")
    def test_stop__calls_controller_stop(self, mock_controller_cls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        server = SMTPServer()
        server.start()
        server.stop()
        assert mock_controller.stop.call_count == 2

    def test_stop__without_start(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        server.stop()
        assert server.controllers == []
