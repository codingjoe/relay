import datetime

from django.db import migrations
from django.utils import timezone

from accounts.models import Organization
from services.email.dashboard import tasks
from services.email.dashboard.onboarding import get_onboarding_state

# The migration Job runs before the Deployments roll, so leave the old workers
# time to be replaced before the first task can be picked up.
ROLLOUT_GRACE = datetime.timedelta(minutes=10)


def schedule_onboarding(apps, schema_editor):
    """Queue the sequence for every organization that has not finished onboarding."""
    run_after = timezone.now() + ROLLOUT_GRACE
    for organization in Organization.objects.filter(suspended_at__isnull=True):
        if not get_onboarding_state(organization)["onboarding_complete"]:
            tasks.schedule_onboarding_emails.using(run_after=run_after).enqueue(
                org_pk=organization.pk,
                from_now=True,
            )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0003_move_github_social_accounts"),
    ]

    operations = [
        migrations.RunPython(schedule_onboarding, migrations.RunPython.noop),
    ]
