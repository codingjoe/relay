from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domains", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="domain",
            old_name="dkim_error",
            new_name="dkim_rsa2048_error",
        ),
        migrations.RenameField(
            model_name="domain",
            old_name="dkim_status",
            new_name="dkim_rsa2048_status",
        ),
        migrations.AlterField(
            model_name="domain",
            name="dkim_rsa2048_error",
            field=models.TextField(
                blank=True,
                help_text="Failure detail if the RSA-2048 DKIM CNAME is incorrect.",
                verbose_name="RSA-2048 DKIM error",
            ),
        ),
        migrations.AlterField(
            model_name="domain",
            name="dkim_rsa2048_status",
            field=models.TextField(
                choices=[
                    ("ok", "ok"),
                    ("error", "error"),
                    ("pending", "pending"),
                    ("unchecked", "unchecked"),
                ],
                default="unchecked",
                help_text="RSA-2048 DKIM CNAME check result on the root domain.",
                verbose_name="RSA-2048 DKIM status",
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="dkim_ed25519_error",
            field=models.TextField(
                blank=True,
                help_text="Failure detail if the Ed25519 DKIM CNAME is incorrect.",
                verbose_name="Ed25519 DKIM error",
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="dkim_ed25519_status",
            field=models.TextField(
                choices=[
                    ("ok", "ok"),
                    ("error", "error"),
                    ("pending", "pending"),
                    ("unchecked", "unchecked"),
                ],
                default="unchecked",
                help_text="Ed25519 DKIM CNAME check result on the root domain.",
                verbose_name="Ed25519 DKIM status",
            ),
        ),
    ]
