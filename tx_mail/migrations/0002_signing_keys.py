"""Seed the test bundle's signing keys.

The encrypted private key is Fernet-encrypted with the project's
KMS key, so it is not portable across installs (a hand-written
fixture would store ciphertext no other machine could decrypt).
Creating the rows here lets the local KMS key encrypt the material
while keeping ``loaddata`` independent of any extra seed command.
This is the standard Django idiom for fixture data that depends on
runtime secrets -- see
https://docs.djangoproject.com/en/6.0/howto/initial-data/.
"""

from django.db import migrations

from kms.models import SigningKey


def create_signing_keys(apps, schema_editor):
    """Generate the three signing keys referenced by ``acme.com``."""
    for algorithm in ("rsa-2048", "rsa-1024", "ed25519"):
        SigningKey.generate(algorithm)


def remove_signing_keys(apps, schema_editor):
    """Reverse: drop the three signing keys."""
    SigningKey.objects.filter(
        algorithm__in=("rsa-2048", "rsa-1024", "ed25519")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tx_mail", "0001_initial"),
        ("kms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_signing_keys, remove_signing_keys),
    ]
