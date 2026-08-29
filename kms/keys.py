"""Asymmetric key generation, encryption, and signing helpers."""

import base64
import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import keystore


class Algorithm:
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
    ciphertext: str  # Fernet-encrypted PEM
    public_key_pem: str  # plaintext PEM
    key_id: str  # short SHA256 prefix of public key
    algorithm: str


def generate_rsa_private_key(key_size: int) -> str:
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
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("ascii")
    )


def public_pem_from_private(private_pem: str) -> str:
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


def key_id_from_public_pem(public_pem: str) -> str:
    return hashlib.sha256(public_pem.encode()).hexdigest()[:16]


def load_public_pem(public_pem: str):
    return serialization.load_pem_public_key(public_pem.encode())


def generate(algorithm: str) -> KeyPair:
    match algorithm:
        case "rsa-2048":
            private_pem = generate_rsa_private_key(2048)
        case "rsa-1024":
            private_pem = generate_rsa_private_key(1024)
        case "ed25519":
            private_pem = generate_ed25519_private_key()
        case _:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    public_pem = public_pem_from_private(private_pem)
    return KeyPair(
        ciphertext=keystore.encrypt(private_pem),
        public_key_pem=public_pem,
        key_id=key_id_from_public_pem(public_pem),
        algorithm=algorithm,
    )


def decrypt(ciphertext: str) -> str:
    return keystore.decrypt(ciphertext)


def load(ciphertext: str):
    pem = decrypt(ciphertext).encode("ascii")
    return serialization.load_pem_private_key(pem, password=None)


def dkim_key_material_from_pem(private_pem: str, algorithm: str) -> tuple[bytes, bytes]:
    match algorithm:
        case Algorithm.RSA_2048 | Algorithm.RSA_1024:
            return private_pem.encode("ascii"), b"rsa-sha256"
        case Algorithm.ED25519:
            private = serialization.load_pem_private_key(private_pem.encode(), None)
            raw_seed = private.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            return base64.b64encode(raw_seed), b"ed25519-sha256"
        case _:
            raise ValueError(f"Unsupported algorithm for DKIM: {algorithm}")


def dkim_key_material(ciphertext: str, algorithm: str) -> tuple[bytes, bytes]:
    return dkim_key_material_from_pem(decrypt(ciphertext), algorithm)
