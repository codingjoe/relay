from django.conf import settings
from django.core.management.base import BaseCommand

from services.email.smtp.server import run_smtp_server


class Command(BaseCommand):
    help = "Run the SMTP server"

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Listen port (overrides RELAY_SMTP_SUBMISSION_PORTS)",
        )

    def handle(self, *args, **options):
        host = options["host"] or settings.RELAY_SMTP_LISTEN_HOST
        ports = (
            [options["port"]]
            if options["port"]
            else settings.RELAY_SMTP_SUBMISSION_PORTS
        )
        self.stdout.write(
            self.style.SUCCESS(f"SMTP server listening on {host}:{ports}")
        )

        run_smtp_server(
            host=host,
            ports=ports,
            implicit_tls_ports=settings.RELAY_SMTP_IMPLICIT_TLS_PORTS,
            tls_cert_path=settings.RELAY_SMTP_TLS_CERT_PATH,
            tls_key_path=settings.RELAY_SMTP_TLS_KEY_PATH,
            proxy_protocol_timeout=settings.RELAY_PROXY_PROTOCOL_TIMEOUT,
        )
