"""MX receiving server with STARTTLS support."""

import logging
import signal
import ssl
import sys
import time

from aiosmtpd.controller import Controller

from .handlers import MXHandler

logger = logging.getLogger(__name__)


class MXServer:
    """Receive incoming MX mail delivery over SMTP, optionally with STARTTLS."""

    def __init__(
        self,
        host="0.0.0.0",
        port=25,
        max_message_size=10 * (1024**2),  # 10 MB
        tls_cert_path="",
        tls_key_path="",
    ):
        self.host = host
        self.port = port
        self.max_message_size = max_message_size
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.controller = None

    def build_tls_context(self):
        """Build the STARTTLS context, or return None when no cert is configured."""
        if not self.tls_cert_path or not self.tls_key_path:
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.tls_cert_path, self.tls_key_path)
        return context

    def start(self):
        handler = MXHandler()
        self.controller = Controller(
            handler,
            hostname=self.host,
            port=self.port,
            tls_context=self.build_tls_context(),
            auth_require_tls=False,
        )
        self.controller.start()
        logger.info(f"MX server listening on {self.host}:{self.port}")

    def stop(self):
        if self.controller:
            self.controller.stop()
            logger.info("MX server stopped")


def run_mx_server(
    host="0.0.0.0",
    port=25,
    max_message_size=10 * (1024**2),  # 10 MB
    tls_cert_path="",
    tls_key_path="",
):
    """Run the MX receiving server until interrupted."""
    server = MXServer(
        host=host,
        port=port,
        max_message_size=max_message_size,
        tls_cert_path=tls_cert_path,
        tls_key_path=tls_key_path,
    )
    server.start()

    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        time.sleep(1)
