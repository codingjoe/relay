import pytest
from django.contrib.auth.models import User

from accounts.models import Membership, Organization


@pytest.mark.django_db
class TestOrganizationListView:
    def test_get__requires_login(self, client, org):
        response = client.get("/organizations/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__redirects_single_org_user(self, admin_client, org):
        response = admin_client.get("/organizations/")
        assert response.status_code == 302
        assert response.url == f"/org/{org.slug}/"

    def test_get__shows_user_orgs(self, admin_client, user, org):
        second_org = Organization.objects.create(slug="second-org")
        Membership.objects.create(
            org=second_org,
            user=user,
            role=Membership.Role.ADMIN,
        )
        other_org = Organization.objects.create(slug="other")
        Membership.objects.create(
            org=other_org,
            user=User.objects.create_user(username="carol", email="c@example.com"),
            role=Membership.Role.ADMIN,
        )
        response = admin_client.get("/organizations/")
        assert response.status_code == 200
        orgs = list(response.context["organizations"])
        assert org in orgs
        assert second_org in orgs
        assert other_org not in orgs

    def test_post__creates_org_and_admin_membership(self, admin_client, user):
        response = admin_client.post("/organizations/", {"slug": "new-org"})
        assert response.status_code == 302
        org = Organization.objects.get(slug="new-org")
        assert response.url.endswith(f"/org/{org.slug}/")
        assert Membership.objects.filter(
            org=org, user=user, role=Membership.Role.ADMIN
        ).exists()

    def test_post__invalid_form_re_renders(self, admin_client):
        response = admin_client.post("/organizations/", {"slug": ""})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_post__rejects_slug_longer_than_dns_label(self, admin_client):
        response = admin_client.post("/organizations/", {"slug": "a" * 64})
        assert response.status_code == 200
        assert "slug" in response.context["form"].errors


@pytest.mark.django_db
class TestOrganizationDetailView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/settings/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/settings/")
        assert response.status_code == 200
        assert response.context["organization"] == org

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/settings/")
        assert response.status_code == 404

    def test_get__context_has_memberships_and_is_admin(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/settings/")
        assert response.context["is_admin"] is True
        assert list(response.context["memberships"]) == list(
            org.memberships.select_related("user")
        )

    def test_get__renders_org_switcher_for_all_member_orgs(
        self, admin_client, user, org
    ):
        second_org = Organization.objects.create(slug="second-org")
        Membership.objects.create(
            org=second_org,
            user=user,
            role=Membership.Role.ADMIN,
        )
        other_org = Organization.objects.create(slug="unrelated-org")
        Membership.objects.create(
            org=other_org,
            user=User.objects.create_user(username="carol", email="c@example.com"),
            role=Membership.Role.ADMIN,
        )
        response = admin_client.get(f"/org/{org.slug}/settings/")
        assert response.status_code == 200
        assert set(response.context["user_orgs"]) == {org, second_org}
        body = response.content.decode()
        assert second_org.slug in body
        assert "unrelated-org" not in body


@pytest.mark.django_db
class TestOrganizationUpdateView:
    def test_get__requires_admin(self, client, org, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/settings/edit")
        assert response.status_code == 403

    def test_get__admin_can_access(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/settings/edit")
        assert response.status_code == 200

    def test_post__changes_slug(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/settings/edit", {"slug": "renamed"}
        )
        assert response.status_code == 302
        org.refresh_from_db()
        assert org.slug == "renamed"

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/settings/edit")
        assert response.status_code == 404


@pytest.mark.django_db
class TestOrganizationDeleteView:
    def test_get__requires_admin(self, client, org, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/settings/delete")
        assert response.status_code == 403

    def test_get__admin_can_access(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/settings/delete")
        assert response.status_code == 200

    def test_post__removes_org(self, admin_client, org):
        response = admin_client.post(f"/org/{org.slug}/settings/delete")
        assert response.status_code == 302
        assert not Organization.objects.filter(pk=org.pk).exists()

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/settings/delete")
        assert response.status_code == 404


@pytest.mark.django_db
class TestMembershipCreateView:
    def test_get__requires_admin(self, client, org, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/settings/members/new")
        assert response.status_code == 403

    def test_post__adds_member(self, admin_client, org, other_user):
        response = admin_client.post(
            f"/org/{org.slug}/settings/members/new",
            {"username": "bob", "role": "write"},
        )
        assert response.status_code == 302
        assert Membership.objects.filter(
            org=org, user=other_user, role=Membership.Role.WRITE
        ).exists()

    def test_post__unknown_user_shows_error(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/settings/members/new",
            {"username": "ghost", "role": "write"},
        )
        assert response.status_code == 200
        assert response.context["member_form"].errors

    def test_post__invalid_form_re_renders(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/settings/members/new",
            {"username": "", "role": "write"},
        )
        assert response.status_code == 200
        assert response.context["member_form"].errors

    def test_post__idempotent_for_existing_member(self, admin_client, org, user):
        response = admin_client.post(
            f"/org/{org.slug}/settings/members/new",
            {"username": "alice", "role": "write"},
        )
        assert response.status_code == 302
        assert Membership.objects.filter(org=org, user=user).count() == 1

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/settings/members/new")
        assert response.status_code == 404


@pytest.mark.django_db
class TestMembershipDeleteView:
    def test_get__requires_admin(self, client, org, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        client.force_login(other_user)
        membership = Membership.objects.get(org=org, user=other_user)
        response = client.get(
            f"/org/{org.slug}/settings/members/{membership.pk}/delete"
        )
        assert response.status_code == 403

    def test_post__removes_member(self, admin_client, org, other_user):
        m = Membership.objects.create(
            org=org, user=other_user, role=Membership.Role.WRITE
        )
        response = admin_client.post(f"/org/{org.slug}/settings/members/{m.pk}/delete")
        assert response.status_code == 302
        assert not Membership.objects.filter(pk=m.pk).exists()

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        membership = write_org.memberships.first()  # noqa: any membership
        response = admin_client.get(
            f"/org/{write_org.slug}/settings/members/{membership.pk}/delete"
        )
        assert response.status_code == 404
