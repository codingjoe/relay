from django.conf import settings


def encrypt(plaintext: str) -> str:
    return settings.FERNET.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return settings.FERNET.decrypt(ciphertext.encode()).decode()
