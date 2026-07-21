import pytest

from domains.models import Domain
from smtp.models import OutgoingMessage


@pytest.mark.django_db
class TestDashboardView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/")
        assert response.status_code == 404

    def test_get__shows_counts(self, admin_client, org, user):
        Domain.objects.create(name="a.com", org=org)
        Domain.objects.create(name="b.com", org=org)
        OutgoingMessage.objects.create(
            sender=user, org=org, rcpt_to="x@example.com", mail_from="y@example.com"
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["total_domains"] == 2
        assert response.context["total_messages"] == 1

    def test_get__context_has_free_sender_domain(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert "free_sender_domain" in response.context

    def test_get__counts_scoped_to_org(self, admin_client, org, write_org, user):
        Domain.objects.create(name="other.com", org=write_org)
        OutgoingMessage.objects.create(
            sender=user,
            org=write_org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.context["total_domains"] == 0
        assert response.context["total_messages"] == 0
