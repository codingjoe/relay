from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kms.models import SigningKey


class Command(BaseCommand):
    """Verify or rotate signing-key ciphertext to the primary Fernet key."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Rotate all signing-key ciphertext after verification.",
        )

    def handle(self, *args, **options):
        if not settings.KMS_FERNET_LEGACY_KEYS:
            raise CommandError(
                "KMS_FERNET_LEGACY_KEYS must contain the previous key during rotation."
            )

        apply_rotation = options["apply"]
        rotated_count = 0
        with transaction.atomic():
            signing_keys = SigningKey.objects.select_for_update().iterator(
                chunk_size=100
            )
            for signing_key in signing_keys:
                try:
                    rotated_ciphertext = settings.FERNET.rotate(
                        signing_key.encrypted_private_key.encode()
                    ).decode()
                    settings.FERNET.decrypt(rotated_ciphertext.encode())
                except (InvalidToken, ValueError) as error:
                    raise CommandError(
                        f"Signing key {signing_key.pk} could not be rotated."
                    ) from error
                if apply_rotation:
                    signing_key.encrypted_private_key = rotated_ciphertext
                    signing_key.save(
                        update_fields=["encrypted_private_key", "modified_at"]
                    )
                rotated_count += 1

            if not apply_rotation:
                transaction.set_rollback(True)

        action = "Rotated" if apply_rotation else "Verified"
        self.stdout.write(self.style.SUCCESS(f"{action} {rotated_count} signing keys."))
