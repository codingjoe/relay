from django.db import migrations, models


def backfill_webhook_delivery_times(apps, schema_editor):
    """Backfill legacy webhook delivery times with the record creation time."""
    delivery = apps.get_model("mta", "webhookdelivery")
    delivery.objects.filter(started_at__isnull=True).update(
        started_at=models.F("created_at"),
        finished_at=models.F("created_at"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("mta", "0002_incomingmessage_tls_certificate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookdelivery",
            name="finished_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the timing finished.",
                null=True,
                verbose_name="finished",
            ),
        ),
        migrations.AddField(
            model_name="webhookdelivery",
            name="started_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the timing started.",
                null=True,
                verbose_name="started",
            ),
        ),
        migrations.RunPython(
            backfill_webhook_delivery_times, migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name="webhookdelivery",
            name="finished_at",
            field=models.DateTimeField(
                db_index=True,
                help_text="When the timing finished.",
                verbose_name="finished",
            ),
        ),
        migrations.AlterField(
            model_name="webhookdelivery",
            name="started_at",
            field=models.DateTimeField(
                db_index=True,
                help_text="When the timing started.",
                verbose_name="started",
            ),
        ),
    ]
