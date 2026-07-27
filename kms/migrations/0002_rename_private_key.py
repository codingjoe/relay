from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("kms", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="signingkey",
            old_name="private_key",
            new_name="encrypted_private_key",
        ),
    ]
