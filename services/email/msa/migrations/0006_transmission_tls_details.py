import django.db.models.deletion
from django.db import migrations, models


def mark_historical_starttls(apps, schema_editor):
    """Record STARTTLS for historical transmissions flagged as sent with SSL.

    Outbound delivery only negotiates STARTTLS, so the boolean flag maps to
    STARTTLS. The presented certificates were never recorded before.
    """
    transmission = apps.get_model("msa", "Transmission")
    transmission.objects.filter(sent_with_ssl=True).update(tls_mode="starttls")


def restore_sent_with_ssl(apps, schema_editor):
    """Restore the boolean SSL flag from the TLS mode."""
    transmission = apps.get_model("msa", "Transmission")
    transmission.objects.filter(tls_mode__in=["starttls", "tls"]).update(
        sent_with_ssl=True
    )
    transmission.objects.exclude(tls_mode__in=["starttls", "tls"]).update(
        sent_with_ssl=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("kms", "0003_certificate"),
        ("msa", "0005_outgoingmessage_feedback_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="transmission",
            name="mx_host",
            field=models.TextField(
                blank=True,
                help_text="MX hostname this delivery attempt dialed.",
                verbose_name="MX host",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transmissions",
                to="kms.certificate",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_cipher",
            field=models.TextField(
                blank=True,
                help_text="Negotiated TLS cipher suite.",
                verbose_name="TLS cipher",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_mode",
            field=models.TextField(
                choices=[
                    ("plaintext", "plaintext"),
                    ("starttls", "STARTTLS"),
                    ("tls", "TLS"),
                ],
                default="plaintext",
                help_text="TLS transport negotiated for this delivery attempt.",
                verbose_name="TLS mode",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_version",
            field=models.TextField(
                blank=True,
                help_text="Negotiated TLS protocol version, for example TLSv1.3.",
                verbose_name="TLS version",
            ),
        ),
        migrations.RunPython(
            mark_historical_starttls,
            reverse_code=restore_sent_with_ssl,
        ),
        migrations.RemoveField(
            model_name="transmission",
            name="sent_with_ssl",
        ),
    ]
