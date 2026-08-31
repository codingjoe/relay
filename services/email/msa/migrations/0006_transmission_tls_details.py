from django.db import migrations, models


def mark_historical_starttls(apps, schema_editor):
    """Record STARTTLS for historical transmissions flagged as sent with SSL.

    Outbound delivery only negotiates STARTTLS, so the boolean flag maps to
    STARTTLS. The remaining TLS details were never recorded before.
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
            name="tls_certificate_chain",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Subjects and SHA-256 fingerprints of the certificate "
                    "chain the remote server presented, one per line."
                ),
                verbose_name="TLS certificate chain",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_fingerprint",
            field=models.TextField(
                blank=True,
                help_text="SHA-256 fingerprint of the remote server's TLS certificate.",
                verbose_name="TLS certificate fingerprint",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_issuer",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Certificate authority that signed the remote server's "
                    "TLS certificate."
                ),
                verbose_name="TLS certificate issuer",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_not_after",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Point in time until which the remote server's TLS "
                    "certificate is valid."
                ),
                null=True,
                verbose_name="TLS certificate valid until",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_not_before",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Point in time from which the remote server's TLS "
                    "certificate is valid."
                ),
                null=True,
                verbose_name="TLS certificate valid from",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_serial_number",
            field=models.TextField(
                blank=True,
                help_text="Serial number of the remote server's TLS certificate.",
                verbose_name="TLS certificate serial number",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_subject",
            field=models.TextField(
                blank=True,
                help_text="Subject of the remote server's TLS certificate.",
                verbose_name="TLS certificate subject",
            ),
        ),
        migrations.AddField(
            model_name="transmission",
            name="tls_certificate_subject_alternative_names",
            field=models.TextField(
                blank=True,
                help_text="DNS names the remote server's TLS certificate covers.",
                verbose_name="TLS certificate subject alternative names",
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
