"""aiosmtpd SMTP server."""

import logging
import signal
import sys
import time

from aiosmtpd.controller import Controller

from .handlers import SMTPHandler

logger = logging.getLogger(__name__)


class SMTPServer:
    """Wrap aiosmtpd to serve outgoing SMTP submissions."""

    def __init__(self, host="0.0.0.0", port=25, max_message_size=10485760):
        self.host = host
        self.port = port
        self.max_message_size = max_message_size
        self.controller = None

    def start(self):
        handler = SMTPHandler()
        self.controller = Controller(
            handler,
            hostname=self.host,
            port=self.port,
            auth_require_tls=False,
        )
        self.controller.start()
        logger.info(f"SMTP server listening on {self.host}:{self.port}")

    def stop(self):
        if self.controller:
            self.controller.stop()
            logger.info("SMTP server stopped")


def run_smtp_server(host="0.0.0.0", port=25, max_message_size=10485760):
    """Run the SMTP submission server until interrupted."""
    server = SMTPServer(host=host, port=port, max_message_size=max_message_size)
    server.start()

    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        time.sleep(1)
