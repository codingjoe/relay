import pytest
from django.db import IntegrityError

from accounts.models import Membership, MembershipEncryptionKey, UserEncryptionKey
from kms import envelope
from kms.models import OrgEncryptionKey


def _make_org_encryption_key(org, is_active=True):
    """Create an OrgEncryptionKey with a fresh X25519 keypair."""
    pair = envelope.generate_org_keypair()
    return OrgEncryptionKey.objects.create(
        org=org,
        public_key=envelope.encode_key(pair.public_key),
        key_id=envelope.key_fingerprint(pair.public_key),
        is_active=is_active,
    )


@pytest.mark.django_db
class TestUserEncryptionKeyCreate:
    def test_create__persists_fields(self, user):
        pair = envelope.generate_org_keypair()
        public_key = envelope.encode_key(pair.public_key)
        key_id = envelope.key_fingerprint(pair.public_key)
        key = UserEncryptionKey.objects.create(
            user=user,
            public_key=public_key,
            encrypted_master_key="emk",
            encrypted_private_key="epk",
            key_id=key_id,
        )
        key.refresh_from_db()
        assert key.user == user
        assert key.public_key == public_key
        assert key.encrypted_master_key == "emk"
        assert key.encrypted_private_key == "epk"
        assert key.key_id == key_id

    def test_str__shows_user_and_key_id(self, user):
        pair = envelope.generate_org_keypair()
        key_id = envelope.key_fingerprint(pair.public_key)
        key = UserEncryptionKey.objects.create(
            user=user,
            public_key=envelope.encode_key(pair.public_key),
            encrypted_master_key="emk",
            encrypted_private_key="epk",
            key_id=key_id,
        )
        assert str(key) == f"{user} / {key_id}"


@pytest.mark.django_db
class TestUserEncryptionKeyConstraints:
    def test_unique__user_and_key_id(self, user):
        pair = envelope.generate_org_keypair()
        key_id = envelope.key_fingerprint(pair.public_key)
        UserEncryptionKey.objects.create(
            user=user,
            public_key=envelope.encode_key(pair.public_key),
            encrypted_master_key="emk",
            encrypted_private_key="epk",
            key_id=key_id,
        )
        other_pair = envelope.generate_org_keypair()
        with pytest.raises(IntegrityError):
            UserEncryptionKey.objects.create(
                user=user,
                public_key=envelope.encode_key(other_pair.public_key),
                encrypted_master_key="emk2",
                encrypted_private_key="epk2",
                key_id=key_id,
            )


@pytest.mark.django_db
class TestMembershipEncryptionKeyCreate:
    def test_create__persists_fields(self, org, user):
        membership = Membership.objects.get(org=org, user=user)
        org_pair = envelope.generate_org_keypair()
        org_key = OrgEncryptionKey.objects.create(
            org=org,
            public_key=envelope.encode_key(org_pair.public_key),
            key_id=envelope.key_fingerprint(org_pair.public_key),
            is_active=True,
        )
        member_pair = envelope.generate_org_keypair()
        sealed = envelope.seal_org_private_key(
            org_pair.private_key, member_pair.public_key
        )
        mek = MembershipEncryptionKey.objects.create(
            membership=membership,
            org_encryption_key=org_key,
            sealed_org_private_key=envelope.encode_key(sealed),
        )
        mek.refresh_from_db()
        assert mek.membership == membership
        assert mek.org_encryption_key == org_key
        assert mek.sealed_org_private_key == envelope.encode_key(sealed)

    def test_str__shows_membership_and_key_id(self, org, user):
        membership = Membership.objects.get(org=org, user=user)
        org_key = _make_org_encryption_key(org)
        member_pair = envelope.generate_org_keypair()
        sealed = envelope.seal_org_private_key(
            envelope.generate_org_keypair().private_key, member_pair.public_key
        )
        mek = MembershipEncryptionKey.objects.create(
            membership=membership,
            org_encryption_key=org_key,
            sealed_org_private_key=envelope.encode_key(sealed),
        )
        assert str(mek) == f"{membership} / {org_key.key_id}"


@pytest.mark.django_db
class TestMembershipEncryptionKeyConstraints:
    def test_one_to_one__only_one_per_membership(self, org, user):
        membership = Membership.objects.get(org=org, user=user)
        org_key = _make_org_encryption_key(org)
        member_pair = envelope.generate_org_keypair()
        sealed = envelope.seal_org_private_key(
            envelope.generate_org_keypair().private_key, member_pair.public_key
        )
        MembershipEncryptionKey.objects.create(
            membership=membership,
            org_encryption_key=org_key,
            sealed_org_private_key=envelope.encode_key(sealed),
        )
        with pytest.raises(IntegrityError):
            MembershipEncryptionKey.objects.create(
                membership=membership,
                org_encryption_key=org_key,
                sealed_org_private_key=envelope.encode_key(sealed),
            )
