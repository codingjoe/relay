from django.conf import settings
from django.core.management.base import BaseCommand

from services.email.mx.server import run_mx_server


class Command(BaseCommand):
    """Run the MX receiving server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0", help="Listen host")
        parser.add_argument(
            "--port",
            action="append",
            type=int,
            default=None,
            help="Listen port (repeat for multiple, defaults to RELAY_MX_PORTS)",
        )

    def handle(self, *args, **options):
        host = options["host"]
        ports = options["port"] or settings.RELAY_MX_PORTS

        self.stdout.write(self.style.SUCCESS(f"MX server listening on {host}:{ports}"))

        run_mx_server(
            host=host,
            ports=ports,
            tls_cert_path=settings.RELAY_MX_TLS_CERT_PATH,
            tls_key_path=settings.RELAY_MX_TLS_KEY_PATH,
        )
