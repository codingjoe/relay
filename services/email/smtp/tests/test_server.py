from unittest.mock import MagicMock, patch


class TestSmtpServerInit:
    def test_init__defaults(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        assert server.host == "0.0.0.0"
        assert server.port == 25
        assert server.max_message_size == 10485760
        assert server.controller is None

    def test_init__custom(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer(host="127.0.0.1", port=587, max_message_size=1024)
        assert server.host == "127.0.0.1"
        assert server.port == 587
        assert server.max_message_size == 1024


class TestSmtpServerLifecycle:
    @patch("services.email.smtp.server.Controller")
    def test_start__creates_controller(self, mock_controller_cls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        server = SMTPServer()
        server.start()
        assert server.controller is mock_controller
        mock_controller.start.assert_called_once()

    @patch("services.email.smtp.server.Controller")
    def test_stop__calls_controller_stop(self, mock_controller_cls):
        from services.email.smtp.server import SMTPServer

        mock_controller = MagicMock()
        mock_controller_cls.return_value = mock_controller
        server = SMTPServer()
        server.start()
        server.stop()
        mock_controller.stop.assert_called_once()

    def test_stop__without_start(self):
        from services.email.smtp.server import SMTPServer

        server = SMTPServer()
        server.stop()
        assert server.controller is None
