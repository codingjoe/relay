import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0003_move_github_social_accounts"),
    ]

    operations = [
        migrations.CreateModel(
            name="OnboardingMail",
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
                        help_text="Which mail of the sequence went out.",
                        verbose_name="stage",
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        help_text="Organization the mail went to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="onboarding_mails",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "ordering": ("-modified_at", "-created_at"),
                "get_latest_by": "created_at",
                "abstract": False,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("org", "stage"),
                        name="unique_onboarding_mail_per_org",
                    )
                ],
            },
        ),
    ]
