import pytest
from cryptography.fernet import InvalidToken

from kms import keystore


class TestEncryptDecrypt:
    def test_encrypt__returns_fernet_token(self):
        ciphertext = keystore.encrypt("hello world")
        # Fernet tokens are URL-safe base64 starting with version byte 0x80.
        assert ciphertext.startswith("gAAA")  # base64 of b"\x80"

    def test_decrypt__recovers_plaintext(self):
        assert keystore.decrypt(keystore.encrypt("hello world")) == "hello world"

    def test_roundtrip__unicode(self):
        original = "héllo 🌎"
        assert keystore.decrypt(keystore.encrypt(original)) == original

    def test_roundtrip__empty_string(self):
        assert keystore.decrypt(keystore.encrypt("")) == ""

    def test_decrypt__rejects_garbage(self):
        with pytest.raises(InvalidToken):
            keystore.decrypt("not-a-valid-fernet-token")

    def test_encrypt__produces_different_ciphertext_for_same_plaintext(self):
        """Fernet uses a random IV. Encryption is non-deterministic."""
        c1 = keystore.encrypt("hello")
        c2 = keystore.encrypt("hello")
        assert c1 != c2
        # But both decrypt to the same plaintext.
        assert keystore.decrypt(c1) == keystore.decrypt(c2) == "hello"
