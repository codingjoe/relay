"""Seed the test bundle's signing keys.

The encrypted private key is Fernet-encrypted with the project's
KMS key, so it is not portable across installs (a hand-written
fixture would store ciphertext no other machine could decrypt).
Creating the rows here lets the local KMS key encrypt the material
while keeping ``loaddata`` independent of any extra seed command.
This is the standard Django idiom for fixture data that depends on
runtime secrets — see
https://docs.djangoproject.com/en/6.0/howto/initial-data/.
"""

from django.db import migrations

from kms.models import SigningKey


def create_signing_keys(apps, schema_editor):
    """Generate the three signing keys referenced by ``acme.com``.

    The order is fixed (``rsa-2048`` first, then ``rsa-1024``, then
    ``ed25519``) so the fixture's ``dkim_key_*`` references stay
    stable — SigningKey uses integer PKs and the three calls below
    land on 1, 2, 3 on a fresh database. ``SigningKey.generate``
    handles Fernet encryption of the private key using the local
    KMS key, which is exactly what we want: a reproducible
    hand-written fixture cannot do that. The ``acme.com`` row is
    loaded later by ``loaddata`` and sets its own FKs, so this
    migration only creates the keys.
    """
    for algorithm in ("rsa-2048", "rsa-1024", "ed25519"):
        SigningKey.generate(algorithm)


def remove_signing_keys(apps, schema_editor):
    """Reverse: drop the three signing keys.

    Reverse-migrations are rarely run in practice, but keeping this
    idempotent lets ``migrate <tx_mail 0001`` return to the post-0001
    state for debugging.
    """
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
