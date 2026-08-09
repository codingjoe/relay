"""aiosmtpd SMTP server."""

import logging
import signal
import ssl
import sys
import time

from aiosmtpd.controller import Controller

from .handlers import SMTPHandler

logger = logging.getLogger(__name__)


class SMTPServer:
    """Serve outgoing SMTP submissions."""

    def __init__(
        self,
        host="0.0.0.0",
        port=25,
        max_message_size=10485760,
        tls_cert_path="",
        tls_key_path="",
        allow_insecure=False,
    ):
        self.host = host
        self.port = port
        self.max_message_size = max_message_size
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.allow_insecure = allow_insecure
        self.controller = None

    def create_tls_context(self):
        """Create the TLS context required for authenticated submission."""
        if self.allow_insecure:
            return None
        if not self.tls_cert_path or not self.tls_key_path:
            raise ValueError("SMTP TLS certificate and key paths are required.")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.tls_cert_path, self.tls_key_path)
        return context

    def start(self):
        handler = SMTPHandler()
        self.controller = Controller(
            handler,
            hostname=self.host,
            port=self.port,
            data_size_limit=self.max_message_size,
            tls_context=self.create_tls_context(),
            require_starttls=not self.allow_insecure,
            auth_require_tls=not self.allow_insecure,
        )
        self.controller.start()
        logger.info(f"SMTP server listening on {self.host}:{self.port}")

    def stop(self):
        if self.controller:
            self.controller.stop()
            logger.info("SMTP server stopped")


def run_smtp_server(
    host="0.0.0.0",
    port=25,
    max_message_size=10485760,
    tls_cert_path="",
    tls_key_path="",
    allow_insecure=False,
):
    """Run the SMTP submission server until interrupted."""
    if not allow_insecure and (not tls_cert_path or not tls_key_path):
        raise ValueError("SMTP TLS certificate and key paths are required.")
    server = SMTPServer(
        host=host,
        port=port,
        max_message_size=max_message_size,
        tls_cert_path=tls_cert_path,
        tls_key_path=tls_key_path,
        allow_insecure=allow_insecure,
    )
    server.start()

    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        time.sleep(1)
