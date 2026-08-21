"""MX receiving server with STARTTLS support."""

import logging
import signal
import sys
import time

from aiosmtpd.controller import Controller

from services.email.tls import build_tls_context

from .handlers import MXHandler

logger = logging.getLogger(__name__)


class MXServer:
    def __init__(
        self,
        host="0.0.0.0",
        ports=(25,),
        tls_cert_path="",
        tls_key_path="",
        proxy_protocol_timeout=None,
    ):
        self.host = host
        self.ports = ports
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.proxy_protocol_timeout = proxy_protocol_timeout
        self.controllers = []

    def start(self):
        handler = MXHandler()
        tls_context = build_tls_context(self.tls_cert_path, self.tls_key_path)
        try:
            for port in self.ports:
                controller = Controller(
                    handler,
                    hostname=self.host,
                    port=port,
                    tls_context=tls_context,
                    proxy_protocol_timeout=self.proxy_protocol_timeout.total_seconds()
                    if self.proxy_protocol_timeout
                    else None,
                )
                controller.start()
                self.controllers.append(controller)
                logger.info(f"MX server listening on {self.host}:{port}")
        except Exception:
            self.stop()
            raise

    def stop(self):
        for controller in self.controllers:
            controller.stop()
        self.controllers = []
        logger.info("MX server stopped")


def run_mx_server(
    host="0.0.0.0",
    ports=(25,),
    tls_cert_path="",
    tls_key_path="",
    proxy_protocol_timeout=None,
):
    server = MXServer(
        host=host,
        ports=ports,
        tls_cert_path=tls_cert_path,
        tls_key_path=tls_key_path,
        proxy_protocol_timeout=proxy_protocol_timeout,
    )
    server.start()

    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        time.sleep(1)
