from django.core.management.base import BaseCommand

from accounts.models import Organization
from services.email.dashboard import tasks
from services.email.dashboard.onboarding import get_onboarding_state


class Command(BaseCommand):
    """Queue the onboarding sequence for organizations that never received it."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--org",
            action="append",
            default=[],
            help="Organization slug, repeatable. Defaults to every organization.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the organizations without queueing anything.",
        )

    def handle(self, *args, org, dry_run, **options):
        query = Organization.objects.filter(suspended_at__isnull=True)
        if org:
            query = query.filter(slug__in=org)
        targets = [
            organization
            for organization in query.iterator()
            if not get_onboarding_state(organization)["onboarding_complete"]
        ]
        for organization in targets:
            if dry_run:
                self.stdout.write(organization.slug)
            else:
                tasks.schedule_onboarding_emails.enqueue(
                    org_pk=organization.pk,
                    from_now=True,
                )
        verb = "Would queue" if dry_run else "Queued"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} the onboarding sequence for {len(targets)}.")
        )
