import pytest

from accounts.models import Membership, MembershipEncryptionKey, UserEncryptionKey
from kms import envelope
from kms.models import OrgEncryptionKey


def make_org_encryption_key(org):
    pair = envelope.generate_x25519_keypair()
    return OrgEncryptionKey.objects.create(
        org=org,
        public_key=envelope.encode_key(pair.public_key),
        is_active=True,
    )


def make_user_encryption_key(user):
    pair = envelope.generate_x25519_keypair()
    return UserEncryptionKey.objects.create(
        user=user,
        public_key=envelope.encode_key(pair.public_key),
        encrypted_master_key="encrypted-master-key",
        encrypted_private_key="encrypted-private-key",
    )


def setup_payload():
    org_pair = envelope.generate_x25519_keypair()
    user_pair = envelope.generate_x25519_keypair()
    return {
        "org_public_key": envelope.encode_key(org_pair.public_key),
        "org_key_id": envelope.key_fingerprint(org_pair.public_key),
        "user_public_key": envelope.encode_key(user_pair.public_key),
        "user_key_id": envelope.key_fingerprint(user_pair.public_key),
        "encrypted_master_key": "encrypted-master-key",
        "encrypted_private_key": "encrypted-private-key",
        "sealed_org_private_key": "sealed-org-private-key",
        "recovery_sealed_org_private_key": "recovery-sealed-org-private-key",
    }


def user_key_payload():
    pair = envelope.generate_x25519_keypair()
    return {
        "public_key": envelope.encode_key(pair.public_key),
        "key_id": envelope.key_fingerprint(pair.public_key),
        "encrypted_master_key": "encrypted-master-key",
        "encrypted_private_key": "encrypted-private-key",
    }


@pytest.mark.django_db
class TestEncryptionStatusView:
    def test_get__returns_status_when_no_encryption(self, client, user, org):
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/encryption/")
        assert response.status_code == 200
        assert response.json()["org_has_encryption"] is False

    def test_get__returns_status_when_encryption_active(self, client, user, org):
        make_org_encryption_key(org)
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/encryption/")
        assert response.status_code == 200
        assert response.json()["org_has_encryption"] is True

    def test_get__non_member_gets_404(self, client, other_user, org):
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/encryption/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestEncryptionSetupView:
    def test_post__creates_all_keys(self, client, user, org):
        client.force_login(user)
        response = client.post(
            f"/org/{org.slug}/encryption/setup/",
            setup_payload(),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert OrgEncryptionKey.objects.filter(org=org, is_active=True).exists()
        assert UserEncryptionKey.objects.filter(user=user).exists()
        membership = org.memberships.get(user=user)
        assert MembershipEncryptionKey.objects.filter(membership=membership).exists()

    def test_post__non_admin_gets_403(self, client, other_user, org):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.post(
            f"/org/{org.slug}/encryption/setup/",
            setup_payload(),
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_post__conflict_if_already_setup(self, client, user, org):
        make_org_encryption_key(org)
        client.force_login(user)
        response = client.post(
            f"/org/{org.slug}/encryption/setup/",
            setup_payload(),
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_post__non_member_gets_404(self, client, other_user, org):
        client.force_login(other_user)
        response = client.post(
            f"/org/{org.slug}/encryption/setup/",
            setup_payload(),
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestUserEncryptionKeyView:
    def test_get__returns_user_key(self, client, user, org):
        make_user_encryption_key(user)
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/encryption/user-key/")
        assert response.status_code == 200
        body = response.json()
        assert body["encrypted_master_key"] == "encrypted-master-key"
        assert body["encrypted_private_key"] == "encrypted-private-key"

    def test_get__returns_404_when_no_key(self, client, user, org):
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/encryption/user-key/")
        assert response.status_code == 404

    def test_post__creates_user_key(self, client, user, org):
        client.force_login(user)
        response = client.post(
            f"/org/{org.slug}/encryption/user-key/",
            user_key_payload(),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert UserEncryptionKey.objects.filter(user=user).exists()

    def test_put__updates_user_key(self, client, user, org):
        make_user_encryption_key(user)
        client.force_login(user)
        payload = user_key_payload()
        response = client.put(
            f"/org/{org.slug}/encryption/user-key/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 200
        key = UserEncryptionKey.objects.get(user=user)
        assert key.public_key == payload["public_key"]


@pytest.mark.django_db
class TestMembershipEncryptionKeyListView:
    def test_get__lists_membership_keys(self, client, user, org):
        org_key = make_org_encryption_key(org)
        membership = org.memberships.get(user=user)
        MembershipEncryptionKey.objects.create(
            membership=membership,
            org_encryption_key=org_key,
            sealed_org_private_key="sealed",
        )
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/encryption/membership-key/")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["membership_id"] == membership.pk

    def test_get__non_admin_gets_403(self, client, other_user, org):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/encryption/membership-key/")
        assert response.status_code == 403

    def test_post__creates_membership_key(self, client, user, other_user, org):
        org_key = make_org_encryption_key(org)
        member_membership = Membership.objects.create(
            org=org, user=other_user, role=Membership.Role.WRITE
        )
        client.force_login(user)
        response = client.post(
            f"/org/{org.slug}/encryption/membership-key/",
            {
                "membership_id": member_membership.pk,
                "sealed_org_private_key": "sealed-for-bob",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        mk = MembershipEncryptionKey.objects.get(membership=member_membership)
        assert mk.sealed_org_private_key == "sealed-for-bob"
        assert mk.org_encryption_key == org_key

    def test_post__non_admin_gets_403(self, client, other_user, org):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.post(
            f"/org/{org.slug}/encryption/membership-key/",
            {"membership_id": 1, "sealed_org_private_key": "sealed"},
            content_type="application/json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestMembershipEncryptionKeyDeleteView:
    def test_delete__removes_membership_key(self, client, user, org):
        org_key = make_org_encryption_key(org)
        membership = org.memberships.get(user=user)
        MembershipEncryptionKey.objects.create(
            membership=membership,
            org_encryption_key=org_key,
            sealed_org_private_key="sealed",
        )
        client.force_login(user)
        response = client.delete(
            f"/org/{org.slug}/encryption/membership-key/{membership.pk}/delete"
        )
        assert response.status_code == 204
        assert not MembershipEncryptionKey.objects.filter(
            membership=membership
        ).exists()

    def test_delete__non_admin_gets_403(self, client, other_user, org):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.delete(
            f"/org/{org.slug}/encryption/membership-key/{other_user.memberships.get(org=org).pk}/delete"
        )
        assert response.status_code == 403
