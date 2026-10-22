import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def start_campaigns(apps, schema_editor):
    """Start a sequence for every organization that has not finished onboarding."""
    Organization = apps.get_model("accounts", "Organization")
    OutgoingMessage = apps.get_model("msa", "OutgoingMessage")
    MsaCredential = apps.get_model("msa", "MsaCredential")
    OnboardingCampaign = apps.get_model("dashboard", "OnboardingCampaign")
    now = django.utils.timezone.now()
    for org in Organization.objects.iterator():
        has_outgoing_message = OutgoingMessage.objects.filter(org_id=org.pk).exists()
        connected = MsaCredential.objects.filter(
            org_id=org.pk,
            last_used_at__isnull=False,
        ).exists()
        if not (has_outgoing_message and connected):
            OnboardingCampaign.objects.get_or_create(
                org_id=org.pk,
                defaults={"next_send_at": now},
            )


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
                    "stage",
                    models.TextField(
                        choices=[
                            ("welcome", "welcome"),
                            ("first-reminder", "first reminder"),
                            ("second-reminder", "second reminder"),
                            ("last-reminder", "last reminder"),
                        ],
                        default="welcome",
                        help_text="Email the sequence sends next.",
                        verbose_name="stage",
                    ),
                ),
                (
                    "next_send_at",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        default=django.utils.timezone.now,
                        help_text=(
                            "When the next email is due. Empty once the sequence ends."
                        ),
                        null=True,
                        verbose_name="next send",
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When onboarding finished, which stops the sequence.",
                        null=True,
                        verbose_name="completed",
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
