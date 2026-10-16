from django.db import migrations, models


def mark_sandbox_messages(apps, schema_editor):
    """Flag the messages a sandbox credential submitted before the flag existed."""
    outgoing_message = apps.get_model("msa", "OutgoingMessage")
    outgoing_message.objects.filter(
        models.Q(status="sandboxed") | models.Q(credential__type="sandbox")
    ).update(is_sandbox=True)


class Migration(migrations.Migration):
    dependencies = [
        ("msa", "0004_outgoingmessage_is_sandbox"),
    ]

    operations = [
        migrations.RunPython(mark_sandbox_messages, migrations.RunPython.noop),
    ]
