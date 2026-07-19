import pytest
from django.contrib.auth.models import User

from accounts.models import Membership, Organization, generate_api_key


class TestGenerateApiKey:
    def test_generate_api_key__length(self):
        assert len(generate_api_key()) == 32

    def test_generate_api_key__charset(self):
        assert generate_api_key().isalnum()

    def test_generate_api_key__uniqueness(self):
        assert generate_api_key() != generate_api_key()


@pytest.mark.django_db
class TestCredentialSalt:
    def test_salt__returns_class_path(self):
        from smtp.models import SmtpCredential

        cred = SmtpCredential(org=Organization.objects.create(name="O"))
        assert cred.salt == "smtp.models.SmtpCredential"


@pytest.mark.django_db
class TestSetKey:
    def test_set_key__stores_hash_and_prefix(self):
        from smtp.models import SmtpCredential

        cred = SmtpCredential(org=Organization.objects.create(name="O"))
        raw_key = generate_api_key()
        cred.set_key(raw_key)
        assert cred.key_hash != raw_key
        assert cred.key_prefix == raw_key[:8]


@pytest.mark.django_db
class TestVerifyKey:
    def test_verify_key__correct_key(self):
        from smtp.models import SmtpCredential

        org = Organization.objects.create(name="O")
        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        assert cred.last_used_at is None
        assert cred.verify_key(raw_key) is True
        cred.refresh_from_db()
        assert cred.last_used_at is not None

    def test_verify_key__wrong_key(self):
        from smtp.models import SmtpCredential

        org = Organization.objects.create(name="O")
        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        assert cred.verify_key("wrong-key-12345678") is False

    def test_verify_key__does_not_update_last_used_on_failure(self):
        from smtp.models import SmtpCredential

        org = Organization.objects.create(name="O")
        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        cred.verify_key("wrong-key-12345678")
        cred.refresh_from_db()
        assert cred.last_used_at is None


@pytest.mark.django_db
class TestCreateWithKey:
    def test_create_with_key__returns_credential_and_raw_key(self):
        from smtp.models import SmtpCredential

        org = Organization.objects.create(name="O")
        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="prod")
        assert cred.pk is not None
        assert len(raw_key) == 32
        assert cred.key_prefix == raw_key[:8]
        assert cred.org == org
        assert cred.name == "prod"


@pytest.mark.django_db
class TestCredentialHold:
    def test_hold__excluded_from_query(self, user, org):
        from smtp.models import SmtpCredential

        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        cred.hold = True
        cred.save(update_fields=["hold"])
        qs = SmtpCredential.objects.select_related("org").filter(
            key_prefix=raw_key[:8],
            org__memberships__user__username=user.username,
            type__in=[SmtpCredential.Type.SMTP, SmtpCredential.Type.SMTP_IP],
            hold=False,
        )
        assert not qs.exists()

    def test_not_hold__included_in_query(self, user, org):
        from smtp.models import SmtpCredential

        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="test")
        qs = SmtpCredential.objects.select_related("org").filter(
            key_prefix=raw_key[:8],
            org__memberships__user__username=user.username,
            type__in=[SmtpCredential.Type.SMTP, SmtpCredential.Type.SMTP_IP],
            hold=False,
        )
        assert qs.exists()


@pytest.mark.django_db
class TestOrganization:
    def test_str__returns_name(self):
        org = Organization.objects.create(name="Acme Inc")
        assert str(org) == "Acme Inc"

    def test_members__uses_membership_through(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="Acme")
        Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        assert user in org.members.all()
        assert user.organizations.filter(pk=org.pk).exists()


@pytest.mark.django_db
class TestMembership:
    def test_str__includes_user_org_and_role(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="Acme")
        m = Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        assert "alice" in str(m)
        assert "Acme" in str(m)
        assert "admin" in str(m)

    def test_unique_constraint__one_membership_per_org(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="Acme")
        Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        with pytest.raises(Exception):  # noqa: PT011
            Membership.objects.create(org=org, user=user, role=Membership.Role.WRITE)
