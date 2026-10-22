import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django_letter.notifications import Notification
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership, Organization

test_notification = Notification("test-notifiable", "Test notification")


class TestOrganization:
    @pytest.mark.parametrize(
        "slug",
        ["ACME", "acme.example", "acme--inc", "-acme", "acme-", "a" * 64],
    )
    def test_save__rejects_non_dns_slug(self, slug):
        with pytest.raises(ValidationError):
            Organization(slug=slug).save()

    @pytest.mark.django_db
    def test_str__returns_slug(self):
        org = Organization.objects.create(slug="acme-inc")
        assert str(org) == "acme-inc"

    @pytest.mark.django_db
    def test_members__uses_membership_through(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="acme")
        Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        assert user in org.members.all()
        assert user.organizations.filter(pk=org.pk).exists()

    @pytest.mark.django_db
    def test_get_absolute_url__returns_detail_url(self):
        org = Organization.objects.create(slug="acme")
        assert org.get_absolute_url() == reverse(
            "accounts:org-home", kwargs={"org_slug": "acme"}
        )


@pytest.mark.django_db
class TestMembership:
    def test_str__includes_user_org_and_role(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="acme")
        m = Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        assert "alice" in str(m)
        assert "acme" in str(m)
        assert "admin" in str(m)

    def test_unique_constraint__one_membership_per_org(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="acme")
        Membership.objects.create(org=org, user=user, role=Membership.Role.ADMIN)
        with pytest.raises(IntegrityError):
            Membership.objects.create(org=org, user=user, role=Membership.Role.WRITE)


@pytest.mark.django_db
class TestMembershipQuerySet:
    def test_for_notification__yields_every_reachable_member(
        self, org, user, other_user
    ):
        Membership.objects.create(org=org, user=other_user)

        assert [
            membership.user.email
            for membership in Membership.objects.filter(org=org).for_notification(
                test_notification
            )
        ] == ["alice@example.com", "bob@example.com"]

    def test_for_notification__skips_a_disabled_notification(
        self, org, user, other_user
    ):
        Membership.objects.create(org=org, user=other_user)
        NotificationPreference.objects.create(
            email_hash=NotificationPreference._meta.get_field("email_hash").hash_email(
                user.email
            ),
            slug=test_notification.slug,
            enabled=False,
        )

        assert [
            membership.user.email
            for membership in Membership.objects.filter(org=org).for_notification(
                test_notification
            )
        ] == ["bob@example.com"]

    def test_for_notification__skips_members_without_a_usable_address(
        self, org, other_user
    ):
        other_user.is_active = False
        other_user.save(update_fields=["is_active"])
        Membership.objects.create(org=org, user=other_user)
        Membership.objects.create(
            org=org, user=User.objects.create_user(username="carol", email="")
        )

        assert [
            membership.user.email
            for membership in Membership.objects.filter(org=org).for_notification(
                test_notification
            )
        ] == ["alice@example.com"]
