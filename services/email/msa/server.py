"""aiosmtpd SMTP server."""

import logging
import signal
import sys
import time

from aiosmtpd.controller import Controller

from services.email.tls import build_tls_context, wait_for_certificate_and_key

from .handlers import ImplicitTLSHandler, SMTPHandler

logger = logging.getLogger(__name__)


class SMTPServer:
    """Serve outgoing SMTP submissions over TLS only."""

    def __init__(
        self,
        host="0.0.0.0",
        ports=(587, 465),
        implicit_tls_ports=(465,),
        tls_cert_path="",
        tls_key_path="",
    ):
        self.host = host
        self.ports = ports
        self.implicit_tls_ports = implicit_tls_ports
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.controllers = []

    def start(self):
        tls_context = build_tls_context(self.tls_cert_path, self.tls_key_path)
        if (
            any(p in self.implicit_tls_ports for p in self.ports)
            and tls_context is None
        ):
            raise ValueError(
                "Implicit TLS ports require a TLS certificate, but no cert path is configured."
            )
        for port in self.ports:
            if port in self.implicit_tls_ports:
                controller = Controller(
                    ImplicitTLSHandler(),
                    hostname=self.host,
                    port=port,
                    ssl_context=tls_context,
                    auth_require_tls=False,
                )
            else:
                controller = Controller(
                    SMTPHandler(),
                    hostname=self.host,
                    port=port,
                    tls_context=tls_context,
                    require_starttls=True,
                    auth_require_tls=True,
                )
            try:
                controller.start()
            except Exception:
                self.stop()
                raise
            self.controllers.append(controller)
            logger.info(f"SMTP server listening on {self.host}:{port}")

    def stop(self):
        for controller in self.controllers:
            controller.stop()
        self.controllers = []
        logger.info("SMTP server stopped")


def run_smtp_server(
    host="0.0.0.0",
    ports=(587, 465),
    implicit_tls_ports=(465,),
    tls_cert_path="",
    tls_key_path="",
):
    """Run the SMTP submission server until interrupted."""
    server = SMTPServer(
        host=host,
        ports=ports,
        implicit_tls_ports=implicit_tls_ports,
        tls_cert_path=tls_cert_path,
        tls_key_path=tls_key_path,
    )
    wait_for_certificate_and_key(tls_cert_path, tls_key_path)
    server.start()

    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        time.sleep(1)
