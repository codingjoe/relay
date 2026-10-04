import logging

from aiosmtpd.smtp import TLSSetupException

from services.email.session import SessionExceptionMixin


class TestSessionExceptionMixin:
    async def test_handle_exception__logs_tls_setup_failure_at_info(self, caplog):
        error = TLSSetupException()
        error.__cause__ = ConnectionResetError()

        with caplog.at_level(logging.INFO, logger="services.email.session"):
            status = await SessionExceptionMixin().handle_exception(error)

        assert caplog.records[0].levelno == logging.INFO
        assert (
            caplog.records[0].getMessage()
            == "Client failed the TLS handshake: TLSSetupException()"
        )
        assert status == "500 Error: (TLSSetupException) "

    async def test_handle_exception__logs_other_errors_at_error(self, caplog):
        error = RuntimeError("database is gone")

        with caplog.at_level(logging.ERROR, logger="services.email.session"):
            status = await SessionExceptionMixin().handle_exception(error)

        assert caplog.records[0].levelno == logging.ERROR
        assert caplog.records[0].exc_info[0] is RuntimeError
        assert status == "500 Error: (RuntimeError) database is gone"
