from django.conf import settings
from django.core.management.base import BaseCommand

from services.email.mta.server import run_mx_server


class Command(BaseCommand):
    """Run the MX receiving server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            default="0.0.0.0",  # noqa: S104
            help="Listen host",
        )
        parser.add_argument(
            "--ports",
            nargs="+",
            type=int,
            default=[*settings.MX_PORTS],
            help="Listen ports (defaults to MX_PORTS)",
        )

    def handle(self, *args, host, ports, **options):
        self.stdout.write(self.style.SUCCESS(f"MX server listening on {host}:{ports}"))

        run_mx_server(
            host=host,
            ports=ports,
            tls_cert_path=settings.MX_TLS_CERT_PATH,
            tls_key_path=settings.MX_TLS_KEY_PATH,
            proxy_protocol_timeout=settings.PROXY_PROTOCOL_TIMEOUT,
        )
