"""Shared SMTP session error handling for the mail servers."""

import logging

from aiosmtpd.smtp import TLSSetupException

logger = logging.getLogger(__name__)


class SessionExceptionMixin:
    """
    Answer session errors without alerting on peer-side TLS failures.

    aiosmtpd logs every session error at ERROR level with a traceback.
    Public SMTP ports attract failed TLS handshakes, for example scanners
    that speak plaintext at the TLS layer or clients that reset the
    connection mid-handshake. Those are peer failures, not relay errors,
    so they are logged at INFO and stay out of Sentry.
    """

    async def handle_exception(self, error: Exception) -> str:
        """Log a session error by cause and return the SMTP status for it."""
        if isinstance(error, TLSSetupException):
            logger.info("Client failed the TLS handshake: %r", error, exc_info=error)
        else:
            logger.error("SMTP session error: %r", error, exc_info=error)
        # Keep aiosmtpd's default status for errors the client can still see.
        return f"500 Error: ({type(error).__name__}) {error}"
