import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def match_originals(apps, schema_editor):
    """Copy legacy MTI report rows into the standalone table.

    Each legacy `FblReport` row was a two-level MTI copy of an
    `IncomingMessage`. Match the original message by organization and RFC
    `message_id`, skipping the copy rows themselves, and link it via the
    new `message` foreign key. Rows without a match get `message = NULL`.
    """

    FblReportOld = apps.get_model("reputation", "FblReportOld")
    FblReport = apps.get_model("reputation", "FblReport")
    IncomingMessage = apps.get_model("mta", "IncomingMessage")
    OutgoingMessage = apps.get_model("msa", "OutgoingMessage")
    Message = apps.get_model("message", "Message")

    olds = list(FblReportOld.objects.all())
    dup_pks = [old.pk for old in olds]
    for old in olds:
        try:
            match = (
                IncomingMessage.objects.filter(
                    org_id=old.org_id, message_id=old.message_id
                )
                .exclude(pk__in=dup_pks)
                .order_by("-created_at")
                .get()
            )
        except IncomingMessage.DoesNotExist:
            try:
                match = (
                    OutgoingMessage.objects.filter(
                        org_id=old.org_id, message_id=old.message_id
                    )
                    .order_by("-created_at")
                    .get()
                )
            except OutgoingMessage.DoesNotExist:
                match = None
        FblReport.objects.create(
            id=old.pk,
            org_id=old.org_id,
            domain_id=old.domain_id,
            created_at=old.created_at,
            modified_at=old.modified_at or timezone.now(),
            source=old.source,
            feedback_type=old.feedback_type,
            user_agent=old.user_agent,
            version=old.version,
            reporting_org=old.reporting_org,
            reporting_email=old.reporting_email,
            source_ip_address=old.source_ip_address,
            arrival_at=old.arrival_at,
            original_mail_from=old.original_mail_from,
            original_rcpt_to=old.original_rcpt_to,
            original_message_id=old.original_message_id,
            authentication_results=old.authentication_results,
            original_headers=old.original_headers,
            message_id=match.message_ptr_id if match else None,
        )

    # Remove the legacy copy rows and their parent `IncomingMessage` and
    # `Message` rows. The originals are not parent-link targets and survive.
    Message.objects.filter(incomingmessage__pk__in=dup_pks).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_organization_suspended_at"),
        ("domains", "0001_initial"),
        ("message", "0001_initial"),
        ("msa", "0001_initial"),
        ("reputation", "0001_initial"),
    ]

    operations = [
        # Stage the MTI child under a temporary name so its rows survive
        # until the standalone model exists.
        migrations.RenameModel("FblReport", "FblReportOld"),
        migrations.CreateModel(
            name="FblReport",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified_at",
                    models.DateTimeField(
                        auto_now=True,
                        db_index=True,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        help_text="Owning organization.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)ss",
                        to="accounts.organization",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Referenced message: the ARF email received from a "
                            "provider for provider reports, or the message Relay "
                            "flagged for relay-generated reports."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="message.message",
                    ),
                ),
                (
                    "domain",
                    models.ForeignKey(
                        blank=True,
                        help_text="Domain the report is about.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="domains.domain",
                    ),
                ),
                (
                    "source",
                    models.TextField(
                        choices=[("provider", "provider"), ("relay", "relay")],
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
                        fields=["feedback_type"],
                        name="reputation__feedbac_bddb85_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(match_originals, migrations.RunPython.noop),
        migrations.DeleteModel("FblReportOld"),
    ]
