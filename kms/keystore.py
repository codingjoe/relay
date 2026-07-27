from django.conf import settings


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` using the configured Fernet key."""
    return settings.FERNET.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt ``ciphertext`` previously produced by :func:`encrypt`."""
    return settings.FERNET.decrypt(ciphertext.encode()).decode()
