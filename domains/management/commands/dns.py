import signal
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from domains.server import DNSServer


class Command(BaseCommand):
    """Run the authoritative DNS server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument("--port", type=int, default=None, help="Listen port")

    def handle(self, *args, **options):
        host = options["host"] or settings.RELAY_DNS_LISTEN_HOST
        port = options["port"] or settings.RELAY_DNS_LISTEN_PORT

        server = DNSServer(host=host, port=port)
        server.start()

        self.stdout.write(self.style.SUCCESS(f"DNS server listening on {host}:{port}"))

        def signal_handler(sig, frame):
            self.stdout.write("Shutting down DNS server...")
            server.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            time.sleep(1)
