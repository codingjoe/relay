import datetime

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

# Mirrors `OnboardingCampaign.SEND_OFFSETS`: the last email goes out a week in.
SEQUENCE_WINDOW = datetime.timedelta(days=8)


def start_campaigns(apps, schema_editor):
    """Start a sequence for recent organizations that have not finished onboarding."""
    Organization = apps.get_model("accounts", "Organization")
    OutgoingMessage = apps.get_model("msa", "OutgoingMessage")
    MsaCredential = apps.get_model("msa", "MsaCredential")
    OnboardingCampaign = apps.get_model("dashboard", "OnboardingCampaign")
    recent = django.utils.timezone.now() - SEQUENCE_WINDOW
    for org in Organization.objects.filter(created_at__gte=recent).iterator():
        has_outgoing_message = OutgoingMessage.objects.filter(org_id=org.pk).exists()
        connected = MsaCredential.objects.filter(
            org_id=org.pk,
            last_used_at__isnull=False,
        ).exists()
        if not (has_outgoing_message and connected):
            OnboardingCampaign.objects.get_or_create(org_id=org.pk)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0003_move_github_social_accounts"),
        ("msa", "0006_remove_outgoingmessage_feedback_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="OnboardingCampaign",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "modified_at",
                    models.DateTimeField(
                        auto_now=True, db_index=True, verbose_name="modified"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="created"
                    ),
                ),
                (
                    "sent_count",
                    models.PositiveSmallIntegerField(
                        db_index=True,
                        default=0,
                        help_text="How many emails of the sequence have gone out.",
                        verbose_name="sent",
                    ),
                ),
                (
                    "org",
                    models.OneToOneField(
                        help_text="Organization the sequence walks through onboarding.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="onboarding_campaign",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "ordering": ("-modified_at", "-created_at"),
                "get_latest_by": "created_at",
                "abstract": False,
            },
        ),
        migrations.RunPython(start_campaigns, migrations.RunPython.noop),
    ]
