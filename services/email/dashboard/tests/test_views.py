import pytest

from domains.models import Domain
from services.email.msa.models import OutgoingMessage


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
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        OutgoingMessage.objects.create(
            org=org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
            domain=domain,
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["total_domains"] == 3
        assert response.context["total_messages"] == 1

    def test_get__context_has_domains(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert "domains" in response.context

    def test_get__counts_scoped_to_org(self, admin_client, org, write_org, user):
        Domain.objects.create(name="other.com", org=write_org)
        domain = Domain.objects.filter(org=write_org).first()  # noqa: multiple domains per org
        OutgoingMessage.objects.create(
            org=write_org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
            domain=domain,
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.context["total_domains"] == 1
        assert response.context["total_messages"] == 0
