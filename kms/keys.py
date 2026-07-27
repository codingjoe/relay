"""Public-key cryptography helpers used by DKIM keys and webhook signing.

All private keys are encrypted at rest via :mod:`kms.keystore` (Fernet
keyed off ``settings.SECRET_KEY``). Public keys stay in plaintext so they
can be shared with clients (DKIM public keys go in DNS, webhook public
keys go in Standard Webhooks ``whpk_`` format).
"""

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import keystore


class Algorithm:
    """Algorithm labels — kept as strings for stable DB storage."""

    RSA_2048 = "rsa-2048"
    RSA_1024 = "rsa-1024"
    ED25519 = "ed25519"


DEFAULT_DKIM_ALGORITHMS: tuple[str, ...] = (
    Algorithm.RSA_2048,
    Algorithm.RSA_1024,
    Algorithm.ED25519,
)


@dataclass(frozen=True)
class KeyPair:
    """A generated keypair with Fernet-encrypted private PEM and plaintext public PEM."""

    ciphertext: str  # Fernet-encrypted PEM
    public_key_pem: str  # plaintext PEM
    key_id: str  # short SHA256 prefix of public key
    algorithm: str


def generate_rsa_private_key(key_size: int) -> str:
    """Return a PEM-encoded RSA private key (PKCS#8, unencrypted)."""
    return (
        rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("ascii")
    )


def generate_ed25519_private_key() -> str:
    """Return a PEM-encoded Ed25519 private key (PKCS#8, unencrypted)."""
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("ascii")
    )


def _public_pem_from_private(private_pem: str) -> str:
    """Derive the PEM-encoded public key from a private key PEM."""
    private_key = serialization.load_pem_private_key(
        private_pem.encode(), password=None
    )
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def _key_id_from_public_pem(public_pem: str) -> str:
    """Return a 16-char SHA256 fingerprint of the PEM bytes (Standard Webhooks style)."""
    return hashlib.sha256(public_pem.encode()).hexdigest()[:16]


def generate(algorithm: str) -> KeyPair:
    """Generate a keypair for the given algorithm, returning encrypted material."""
    match algorithm:
        case "rsa-2048":
            private_pem = generate_rsa_private_key(2048)
        case "rsa-1024":
            private_pem = generate_rsa_private_key(1024)
        case "ed25519":
            private_pem = generate_ed25519_private_key()
        case _:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    public_pem = _public_pem_from_private(private_pem)
    return KeyPair(
        ciphertext=keystore.encrypt(private_pem),
        public_key_pem=public_pem,
        key_id=_key_id_from_public_pem(public_pem),
        algorithm=algorithm,
    )


def decrypt(ciphertext: str) -> str:
    """Decrypt stored ciphertext to a PEM-encoded private key."""
    return keystore.decrypt(ciphertext)


def load(ciphertext: str):
    """Decrypt a private key and return the in-memory key object."""
    pem = decrypt(ciphertext).encode("ascii")
    return serialization.load_pem_private_key(pem, password=None)
