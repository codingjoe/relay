import signal
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from dnslib.server import DNSLogger, DNSServer

from domains.resolver import DNSResolver


class Command(BaseCommand):
    """Run the authoritative DNS server."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument("--port", type=int, default=None, help="Listen port")

    def handle(self, *args, **options):
        sys.stdout.reconfigure(line_buffering=True)
        host = options["host"] or "0.0.0.0"
        port = options["port"] or 53

        resolver = DNSResolver()
        logger = DNSLogger(
            log="+request,-reply" if settings.DEBUG else "-request,-reply",
            logf=self.stdout.write,
        )
        servers = (
            DNSServer(resolver, address=host, port=port, logger=logger),
            DNSServer(resolver, address=host, port=port, tcp=True, logger=logger),
        )
        for server in servers:
            server.start_thread()

        self.stdout.write(self.style.SUCCESS(f"DNS server listening on {host}:{port}"))

        def signal_handler(sig, frame):
            self.stdout.write("Shutting down DNS server...")
            for server in servers:
                server.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            time.sleep(1)
