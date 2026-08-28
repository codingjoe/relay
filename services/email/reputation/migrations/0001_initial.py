import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("mta", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FblReport",
            fields=[
                (
                    "incomingmessage_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="mta.incomingmessage",
                    ),
                ),
                (
                    "source",
                    models.TextField(
                        choices=[
                            ("provider", "provider"),
                            ("relay", "relay"),
                        ],
                        default="provider",
                        help_text="Provider reports were received from a mailbox provider and count as complaints. Relay-generated reports are records of spam Relay detected itself and are for visibility only.",
                        verbose_name="source",
                    ),
                ),
                (
                    "feedback_type",
                    models.TextField(
                        choices=[
                            ("abuse", "abuse"),
                            ("fraud", "fraud"),
                            ("virus", "virus"),
                            ("not-spam", "not-spam"),
                            ("opt-out", "opt-out"),
                            ("other", "other"),
                        ],
                        default="abuse",
                        help_text="ARF feedback type indicating the nature of the complaint.",
                        verbose_name="feedback type",
                    ),
                ),
                (
                    "user_agent",
                    models.TextField(
                        blank=True,
                        help_text="Reporting system that generated the FBL report.",
                        verbose_name="user agent",
                    ),
                ),
                (
                    "version",
                    models.TextField(
                        blank=True,
                        help_text="ARF version from the feedback report.",
                        verbose_name="version",
                    ),
                ),
                (
                    "reporting_org",
                    models.TextField(
                        blank=True,
                        help_text="Organization that generated the report.",
                        verbose_name="reporting organization",
                    ),
                ),
                (
                    "reporting_email",
                    models.EmailField(
                        blank=True,
                        help_text="Contact email from the report metadata.",
                        max_length=254,
                        verbose_name="reporting email",
                    ),
                ),
                (
                    "source_ip_address",
                    models.GenericIPAddressField(
                        blank=True,
                        help_text="Original sending IP address.",
                        null=True,
                        verbose_name="source IP address",
                    ),
                ),
                (
                    "arrival_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the original message was received by the reporting provider.",
                        null=True,
                        verbose_name="arrival at",
                    ),
                ),
                (
                    "original_mail_from",
                    models.EmailField(
                        blank=True,
                        help_text="Envelope sender of the original message.",
                        max_length=254,
                        verbose_name="original mail from",
                    ),
                ),
                (
                    "original_rcpt_to",
                    models.EmailField(
                        blank=True,
                        help_text="Envelope recipient of the original message.",
                        max_length=254,
                        verbose_name="original rcpt to",
                    ),
                ),
                (
                    "original_message_id",
                    models.TextField(
                        blank=True,
                        help_text="RFC 5322 Message-ID of the original message.",
                        verbose_name="original message ID",
                    ),
                ),
                (
                    "authentication_results",
                    models.TextField(
                        blank=True,
                        help_text="SPF and DKIM authentication results from the report.",
                        verbose_name="authentication results",
                    ),
                ),
                (
                    "original_headers",
                    models.TextField(
                        blank=True,
                        help_text="Headers of the original message from the report.",
                        verbose_name="original headers",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["arrival_at"], name="reputation__arrival_8495bd_idx"
                    ),
                    models.Index(
                        fields=["feedback_type"], name="reputation__feedbac_bddb85_idx"
                    ),
                ],
            },
            bases=("mta.incomingmessage",),
        ),
    ]
