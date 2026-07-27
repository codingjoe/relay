from django.conf import settings
from django.core.management.base import BaseCommand

from mx.server import run_mx_server


class Command(BaseCommand):
    """Run the MX receiving server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument("--port", type=int, default=None, help="Listen port")

    def handle(self, *args, **options):
        host = options["host"] or settings.RELAY_MX_LISTEN_HOST
        port = options["port"] or settings.RELAY_MX_LISTEN_PORT
        max_size = settings.RELAY_MX_MAX_MESSAGE_SIZE

        self.stdout.write(self.style.SUCCESS(f"MX server listening on {host}:{port}"))

        run_mx_server(
            host=host,
            port=port,
            max_message_size=max_size,
            tls_cert_path=settings.RELAY_MX_TLS_CERT_PATH,
            tls_key_path=settings.RELAY_MX_TLS_KEY_PATH,
        )
