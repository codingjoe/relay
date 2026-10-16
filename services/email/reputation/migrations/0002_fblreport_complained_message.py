import django.db.models.deletion
from django.db import migrations, models


def drop_reports_without_a_message(apps, schema_editor):
    """Remove complaints that name no message before the relation is required."""
    fbl_report = apps.get_model("reputation", "FblReport")
    fbl_report.objects.filter(complained_message__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("message", "0002_alter_message_raw_body"),
        ("reputation", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fblreport",
            name="complained_message",
            field=models.ForeignKey(
                help_text="Message the recipient complained about, not the report email. Repeated reports about one message count once.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="message.message",
            ),
        ),
        migrations.RunPython(drop_reports_without_a_message, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fblreport",
            name="complained_message",
            field=models.ForeignKey(
                help_text="Message the recipient complained about, not the report email. Repeated reports about one message count once.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="message.message",
            ),
        ),
        migrations.AlterField(
            model_name="fblreport",
            name="message",
            field=models.ForeignKey(
                help_text="ARF email the provider sent, or the message Relay flagged. Not the message complained about, see complained_message.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="message.message",
            ),
        ),
    ]
