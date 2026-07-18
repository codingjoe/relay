from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the SMTP server"

    def add_arguments(self, parser):
        parser.add_argument("--host", default=None, help="Listen host")
        parser.add_argument("--port", type=int, default=None, help="Listen port")

    def handle(self, *args, **options):
        from django.conf import settings
        from smtp.server import run_smtp_server

        host = options["host"] or settings.RELAY_SMTP_LISTEN_HOST
        port = options["port"] or settings.RELAY_SMTP_LISTEN_PORT
        max_size = settings.RELAY_SMTP_MAX_MESSAGE_SIZE

        self.stdout.write(self.style.SUCCESS(f"SMTP server listening on {host}:{port}"))

        run_smtp_server(host=host, port=port, max_message_size=max_size)
