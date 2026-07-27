import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from kms import keys


class TestGenerateRsaPrivateKey:
    def test_generate_rsa_private_key__2048(self):
        pem = keys.generate_rsa_private_key(2048)
        assert pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert pem.endswith("-----END PRIVATE KEY-----\n")
        # Decoding should yield a working 2048-bit RSA private key.
        private = serialization.load_pem_private_key(pem.encode(), None)
        assert isinstance(private, rsa.RSAPrivateKey)
        assert private.key_size == 2048

    def test_generate_rsa_private_key__1024(self):
        pem = keys.generate_rsa_private_key(1024)
        private = serialization.load_pem_private_key(pem.encode(), None)
        assert isinstance(private, rsa.RSAPrivateKey)
        assert private.key_size == 1024

    def test_generate_rsa_private_key__produces_unique_keys(self):
        """Two consecutive generations must yield distinct keys."""
        pem1 = keys.generate_rsa_private_key(2048)
        pem2 = keys.generate_rsa_private_key(2048)
        assert pem1 != pem2


class TestGenerateEd25519PrivateKey:
    def test_generate_ed25519_private_key__produces_pem(self):
        pem = keys.generate_ed25519_private_key()
        assert pem.startswith("-----BEGIN PRIVATE KEY-----")
        private = serialization.load_pem_private_key(pem.encode(), None)
        assert isinstance(private, Ed25519PrivateKey)

    def test_generate_ed25519_private_key__produces_unique_keys(self):
        pem1 = keys.generate_ed25519_private_key()
        pem2 = keys.generate_ed25519_private_key()
        assert pem1 != pem2


class TestPublicPemFromPrivate:
    def test_public_pem_from_private__rsa_roundtrip(self):
        private_pem = keys.generate_rsa_private_key(2048)
        public_pem = keys.public_pem_from_private(private_pem)
        assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")
        public = serialization.load_pem_public_key(public_pem.encode())
        assert isinstance(public, rsa.RSAPublicKey)
        assert public.key_size == 2048

    def test_public_pem_from_private__ed25519_roundtrip(self):
        private_pem = keys.generate_ed25519_private_key()
        public_pem = keys.public_pem_from_private(private_pem)
        public = serialization.load_pem_public_key(public_pem.encode())
        assert isinstance(public, Ed25519PublicKey)


class TestKeyIdFromPublicPem:
    def test_key_id__is_16_chars(self):
        private_pem = keys.generate_ed25519_private_key()
        public_pem = keys.public_pem_from_private(private_pem)
        key_id = keys.key_id_from_public_pem(public_pem)
        assert len(key_id) == 16
        int(key_id, 16)  # Must be valid hex

    def test_key_id__is_deterministic(self):
        private_pem = keys.generate_ed25519_private_key()
        public_pem = keys.public_pem_from_private(private_pem)
        assert keys.key_id_from_public_pem(public_pem) == keys.key_id_from_public_pem(
            public_pem
        )

    def test_key_id__differs_per_key(self):
        priv1 = keys.generate_ed25519_private_key()
        priv2 = keys.generate_ed25519_private_key()
        pub1 = keys.public_pem_from_private(priv1)
        pub2 = keys.public_pem_from_private(priv2)
        assert keys.key_id_from_public_pem(pub1) != keys.key_id_from_public_pem(pub2)


class TestLoadPublicPem:
    def test_load_public_pem__returns_key_object(self):
        private_pem = keys.generate_ed25519_private_key()
        public_pem = keys.public_pem_from_private(private_pem)
        loaded = keys.load_public_pem(public_pem)
        assert isinstance(loaded, Ed25519PublicKey)


class TestGenerate:
    def test_generate__ed25519(self):
        pair = keys.generate("ed25519")
        assert pair.algorithm == "ed25519"
        assert pair.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert len(pair.key_id) == 16
        assert pair.ciphertext  # Fernet-encrypted, non-empty base64

    def test_generate__rsa_2048(self):
        pair = keys.generate("rsa-2048")
        assert pair.algorithm == "rsa-2048"
        public = keys.load_public_pem(pair.public_key_pem)
        assert isinstance(public, rsa.RSAPublicKey)
        assert public.key_size == 2048

    def test_generate__rsa_1024(self):
        pair = keys.generate("rsa-1024")
        assert pair.algorithm == "rsa-1024"
        public = keys.load_public_pem(pair.public_key_pem)
        assert public.key_size == 1024

    def test_generate__unsupported_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            keys.generate("bogus")


class TestDecrypt:
    def test_decrypt__roundtrip(self):
        pair = keys.generate("ed25519")
        # decrypt must yield a valid private-key PEM.
        pem = keys.decrypt(pair.ciphertext)
        assert pem.startswith("-----BEGIN PRIVATE KEY-----")
        private = serialization.load_pem_private_key(pem.encode(), None)
        assert isinstance(private, Ed25519PrivateKey)


class TestLoad:
    def test_load__returns_key_object(self):
        pair = keys.generate("ed25519")
        private = keys.load(pair.ciphertext)
        assert isinstance(private, Ed25519PrivateKey)

    def test_load__can_sign(self):
        pair = keys.generate("ed25519")
        private = keys.load(pair.ciphertext)
        # Load the public key and verify a signature made by the loaded private key.
        public = keys.load_public_pem(pair.public_key_pem)
        payload = b"hello"
        signature = private.sign(payload)
        public.verify(signature, payload)
