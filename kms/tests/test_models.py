import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import IntegrityError

from kms.models import SigningKey


@pytest.mark.django_db
class TestSigningKeyGenerate:
    def test_generate__persists_with_correct_fields(self):
        key = SigningKey.generate("ed25519")
        assert key.pk is not None
        assert key.algorithm == SigningKey.Algorithm.ED25519
        assert key.public_key.startswith("-----BEGIN PUBLIC KEY-----")
        assert len(key.key_id) == 16
        # Ciphertext is Fernet-encrypted (starts with gAAA in URL-safe base64).
        assert key.encrypted_private_key.startswith("gAAA")

    def test_generate__rsa_2048(self):
        key = SigningKey.generate("rsa-2048")
        assert key.algorithm == SigningKey.Algorithm.RSA_2048

    def test_generate__produces_unique_keys(self):
        k1 = SigningKey.generate("ed25519")
        k2 = SigningKey.generate("ed25519")
        assert k1.key_id != k2.key_id
        assert k1.public_key != k2.public_key


@pytest.mark.django_db
class TestSigningKeySign:
    def test_sign__produces_64_byte_ed25519_signature(self):
        key = SigningKey.generate("ed25519")
        signature = key.sign(b"hello world")
        assert isinstance(signature, bytes)
        assert len(signature) == 64

    def test_sign__verifies_with_public_bytes_raw(self):
        """A signature made by sign() must verify against the raw public key."""
        key = SigningKey.generate("ed25519")
        payload = b"hello world"
        signature = key.sign(payload)
        public = Ed25519PublicKey.from_public_bytes(key.public_bytes_raw())
        public.verify(signature, payload)

    def test_sign__different_payloads_produce_different_signatures(self):
        key = SigningKey.generate("ed25519")
        sig1 = key.sign(b"foo")
        sig2 = key.sign(b"bar")
        assert sig1 != sig2


@pytest.mark.django_db
class TestSigningKeyPublicBytes:
    def test_public_bytes_raw__is_32_bytes_for_ed25519(self):
        key = SigningKey.generate("ed25519")
        raw = key.public_bytes_raw()
        assert len(raw) == 32
        # Should round-trip through Ed25519PublicKey.from_public_bytes.
        Ed25519PublicKey.from_public_bytes(raw)

    def test_public_bytes_raw__matches_public_pem(self):
        """Raw bytes must correspond to the public PEM."""

        key = SigningKey.generate("ed25519")
        raw = key.public_bytes_raw()
        from_pem = serialization.load_pem_public_key(
            key.public_key.encode()
        ).public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        assert raw == from_pem

    def test_public_bytes_der__for_rsa(self):
        """RSA public keys must encode to SPKI DER (used for the DKIM p= tag)."""

        key = SigningKey.generate("rsa-2048")
        der = key.public_bytes_der()
        # Should decode back to the same RSA public key.
        loaded = serialization.load_der_public_key(der)

        assert isinstance(loaded, rsa.RSAPublicKey)
        assert loaded.key_size == 2048


@pytest.mark.django_db
class TestSigningKeyStr:
    def test_str__shows_algorithm_and_key_id(self):
        key = SigningKey.generate("ed25519")
        assert str(key) == f"ed25519/{key.key_id}"


@pytest.mark.django_db
class TestSigningKeyConstraints:
    def test_unique_constraint__per_algorithm_and_key_id(self):
        """Two keys with the same algorithm and key_id cannot coexist."""
        key1 = SigningKey.generate("ed25519")
        # Force a duplicate key_id.
        with pytest.raises(IntegrityError):
            SigningKey.objects.create(
                algorithm=key1.algorithm,
                key_id=key1.key_id,
                public_key=key1.public_key,
                encrypted_private_key=key1.encrypted_private_key,
            )
