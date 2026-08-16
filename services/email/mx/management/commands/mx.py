from django.conf import settings
from django.core.management.base import BaseCommand

from services.email.mx.server import run_mx_server


class Command(BaseCommand):
    """Run the MX receiving server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Listen port (overrides RELAY_MX_PORTS)",
        )

    def handle(self, *args, **options):
        host = options["host"] or settings.RELAY_MX_LISTEN_HOST
        ports = [options["port"]] if options["port"] else settings.RELAY_MX_PORTS
        max_size = settings.RELAY_MX_MAX_MESSAGE_SIZE

        self.stdout.write(self.style.SUCCESS(f"MX server listening on {host}:{ports}"))

        run_mx_server(
            host=host,
            ports=ports,
            implicit_tls_ports=settings.RELAY_MX_IMPLICIT_TLS_PORTS,
            max_message_size=max_size,
            tls_cert_path=settings.RELAY_MX_TLS_CERT_PATH,
            tls_key_path=settings.RELAY_MX_TLS_KEY_PATH,
            proxy_protocol_timeout=settings.RELAY_PROXY_PROTOCOL_TIMEOUT,
        )
