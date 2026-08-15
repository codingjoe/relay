import pytest
from nacl.exceptions import CryptoError

from kms import envelope


class TestGenerateOrgKeypair:
    def test_generate_org_keypair__public_key_is_32_bytes(self):
        pair = envelope.generate_org_keypair()
        assert len(pair.public_key) == 32

    def test_generate_org_keypair__private_key_is_32_bytes(self):
        pair = envelope.generate_org_keypair()
        assert len(pair.private_key) == 32

    def test_generate_org_keypair__different_each_call(self):
        pair1 = envelope.generate_org_keypair()
        pair2 = envelope.generate_org_keypair()
        assert pair1.public_key != pair2.public_key
        assert pair1.private_key != pair2.private_key


class TestGenerateFileKey:
    def test_generate_file_key__is_32_bytes(self):
        assert len(envelope.generate_file_key()) == 32

    def test_generate_file_key__different_each_call(self):
        assert envelope.generate_file_key() != envelope.generate_file_key()


class TestEncryptDecryptBody:
    def test_decrypt_body__recovers_plaintext(self):
        file_key = envelope.generate_file_key()
        ciphertext = envelope.encrypt_body(b"hello world", file_key)
        assert envelope.decrypt_body(ciphertext, file_key) == b"hello world"

    def test_encrypt_body__different_ciphertext_each_call(self):
        file_key = envelope.generate_file_key()
        c1 = envelope.encrypt_body(b"hello", file_key)
        c2 = envelope.encrypt_body(b"hello", file_key)
        assert c1 != c2
        assert envelope.decrypt_body(c1, file_key) == b"hello"
        assert envelope.decrypt_body(c2, file_key) == b"hello"

    def test_decrypt_body__empty_plaintext(self):
        file_key = envelope.generate_file_key()
        ciphertext = envelope.encrypt_body(b"", file_key)
        assert envelope.decrypt_body(ciphertext, file_key) == b""

    def test_decrypt_body__unicode(self):
        file_key = envelope.generate_file_key()
        plaintext = "héllo 🌎".encode()
        ciphertext = envelope.encrypt_body(plaintext, file_key)
        assert envelope.decrypt_body(ciphertext, file_key) == plaintext

    def test_decrypt_body__wrong_key_raises(self):
        ciphertext = envelope.encrypt_body(b"hello", envelope.generate_file_key())
        with pytest.raises(CryptoError):
            envelope.decrypt_body(ciphertext, envelope.generate_file_key())


class TestSealUnsealFileKey:
    def test_unseal_file_key__recovers_original(self):
        pair = envelope.generate_org_keypair()
        file_key = envelope.generate_file_key()
        sealed = envelope.seal_file_key(file_key, pair.public_key)
        assert envelope.unseal_file_key(sealed, pair.private_key) == file_key

    def test_seal_file_key__differs_from_plaintext(self):
        pair = envelope.generate_org_keypair()
        file_key = envelope.generate_file_key()
        sealed = envelope.seal_file_key(file_key, pair.public_key)
        assert sealed != file_key

    def test_unseal_file_key__wrong_private_key_raises(self):
        pair = envelope.generate_org_keypair()
        other = envelope.generate_org_keypair()
        sealed = envelope.seal_file_key(envelope.generate_file_key(), pair.public_key)
        with pytest.raises(CryptoError):
            envelope.unseal_file_key(sealed, other.private_key)


class TestSealUnsealOrgPrivateKey:
    def test_unseal_org_private_key__recovers_original(self):
        org_pair = envelope.generate_org_keypair()
        recipient = envelope.generate_org_keypair()
        sealed = envelope.seal_org_private_key(
            org_pair.private_key, recipient.public_key
        )
        assert (
            envelope.unseal_org_private_key(sealed, recipient.private_key)
            == org_pair.private_key
        )


class TestKeyFingerprint:
    def test_key_fingerprint__is_16_char_hex(self):
        pair = envelope.generate_org_keypair()
        fp = envelope.key_fingerprint(pair.public_key)
        assert len(fp) == 16
        int(fp, 16)

    def test_key_fingerprint__deterministic(self):
        pair = envelope.generate_org_keypair()
        assert envelope.key_fingerprint(pair.public_key) == envelope.key_fingerprint(
            pair.public_key
        )

    def test_key_fingerprint__differs_per_key(self):
        pair1 = envelope.generate_org_keypair()
        pair2 = envelope.generate_org_keypair()
        assert envelope.key_fingerprint(pair1.public_key) != envelope.key_fingerprint(
            pair2.public_key
        )


class TestEncodeDecodeKey:
    def test_decode_key__roundtrip(self):
        key = envelope.generate_file_key()
        assert envelope.decode_key(envelope.encode_key(key)) == key

    def test_encode_key__returns_str(self):
        key = envelope.generate_file_key()
        assert isinstance(envelope.encode_key(key), str)
