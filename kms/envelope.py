import base64
import hashlib
from dataclasses import dataclass

from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.secret import SecretBox
from nacl.utils import random

FILE_KEY_SIZE = 32  # bytes, for XSalsa20-Poly1305


@dataclass(frozen=True)
class X25519KeyPair:
    """An X25519 keypair for sealed-box encryption.

    Only the public key is stored server-side.
    """

    public_key: bytes  # 32 bytes
    private_key: bytes  # 32 bytes


def generate_x25519_keypair() -> X25519KeyPair:
    """Generate a random X25519 keypair."""
    private_key = PrivateKey.generate()
    return X25519KeyPair(
        public_key=bytes(private_key.public_key),
        private_key=bytes(private_key),
    )


def generate_file_key() -> bytes:
    """Generate a random 32-byte file key for symmetric encryption."""
    return random(FILE_KEY_SIZE)


def encrypt_body(plaintext: bytes, file_key: bytes) -> bytes:
    """Encrypt a message body using authenticated symmetric encryption.

    Return the nonce prepended to the ciphertext.
    """
    nonce = random(SecretBox.NONCE_SIZE)
    return nonce + SecretBox(file_key).encrypt(plaintext, nonce).ciphertext


def decrypt_body(ciphertext: bytes, file_key: bytes) -> bytes:
    """Decrypt a message body encrypted with `encrypt_body`."""
    nonce_size = SecretBox.NONCE_SIZE
    return SecretBox(file_key).decrypt(ciphertext[nonce_size:], ciphertext[:nonce_size])


def seal_file_key(file_key: bytes, recipient_public_key: bytes) -> bytes:
    """Seal a file key with a recipient's X25519 public key.

    The sender does not need a keypair; only the recipient can unseal.
    """
    return SealedBox(PublicKey(recipient_public_key)).encrypt(file_key)


def unseal_file_key(sealed: bytes, recipient_private_key: bytes) -> bytes:
    """Unseal a file key sealed with `seal_file_key`.

    Used client-side (browser), not server-side.
    """
    return SealedBox(PrivateKey(recipient_private_key)).decrypt(sealed)


def key_fingerprint(public_key: bytes) -> str:
    """Return a 16-character hex fingerprint of a public key."""
    return hashlib.sha256(public_key).hexdigest()[:16]


def encode_key(key: bytes) -> str:
    """Encode raw key bytes as base64 for storage in a TextField."""
    return base64.b64encode(key).decode("ascii")


def decode_key(encoded: str) -> bytes:
    """Decode a base64-encoded key back to raw bytes."""
    return base64.b64decode(encoded.encode("ascii"))


@dataclass(frozen=True)
class EncryptionResult:
    """Ciphertext and sealed file key produced by seal_and_encrypt."""

    ciphertext: bytes
    sealed_file_key: str
    org_encryption_key_id: str
    file_key: bytes


def seal_and_encrypt(
    plaintext: bytes, recipient_public_key: bytes, key_id: str
) -> EncryptionResult:
    """Encrypt plaintext and seal the file key with the recipient's public key.

    Return the ciphertext (for S3), a base64 sealed file key (for the DB),
    the key ID used for sealing, and the raw file key (for sealing additional
    copies, for example for webhooks). Callers must discard the file key
    after use.
    """
    file_key = generate_file_key()
    ciphertext = encrypt_body(plaintext, file_key)
    sealed = seal_file_key(file_key, recipient_public_key)
    return EncryptionResult(
        ciphertext=ciphertext,
        sealed_file_key=encode_key(sealed),
        org_encryption_key_id=key_id,
        file_key=file_key,
    )
