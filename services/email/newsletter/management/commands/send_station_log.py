from django.core.management.base import BaseCommand, CommandError

from captains_log.content import CaptainsLogContent
from services.email.newsletter.tasks import send_station_log, station_log_recipients


class Command(BaseCommand):
    """Announce a published station log to the members who want it."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Update slug, for example 2026-10.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the recipients without sending.",
        )
        parser.add_argument(
            "--now",
            action="store_true",
            help="Send in this process instead of queueing the task.",
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        if slug not in CaptainsLogContent.slugs:
            raise CommandError(  # noqa: TRY003 -- the slug is the message
                f"Unknown station log {slug!r}."
            )
        if options["dry_run"]:
            recipients = len(station_log_recipients())
            noun = "member" if recipients == 1 else "members"
            self.stdout.write(f"{slug} would reach {recipients} {noun}.")
        elif options["now"]:
            send_station_log.func(slug=slug)
            self.stdout.write(self.style.SUCCESS(f"Sent {slug}."))
        else:
            send_station_log.enqueue(slug=slug)
            self.stdout.write(self.style.SUCCESS(f"Queued {slug}."))
