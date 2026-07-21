import pytest

from domains.models import Domain


@pytest.mark.django_db
class TestDomainListView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/domains/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/domains/")
        assert response.status_code == 200

    def test_get__filters_by_org(self, admin_client, org, write_org):
        Domain.objects.create(name="mine.com", org=org)
        Domain.objects.create(name="theirs.com", org=write_org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/")
        assert response.status_code == 200
        domains = list(response.context["domains"])
        assert len(domains) == 1
        assert domains[0].name == "mine.com"

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/domains/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainCreateView:
    def test_post__creates_domain(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new", {"name": "new.com"}
        )
        assert response.status_code == 302
        domain = Domain.objects.get(name="new.com")
        assert domain.org == org

    def test_post__redirects_to_list(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new", {"name": "new.com"}
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/domains/")


@pytest.mark.django_db
class TestDomainDetailView:
    def test_get__ok_for_member(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert response.status_code == 200
        assert response.context["domain"] == domain

    def test_get__context_has_nameservers(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert "nameservers" in response.context
        assert "spf_include" in response.context

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        domain = Domain.objects.create(name="other.com", org=write_org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainVerifyView:
    def test_post__redirects_to_detail(self, admin_client, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(domain.name, "TXT", "v=spf1 include:spf.localhost ~all")
        dns_resolver.add(
            domain.dkim_cname_name,
            "CNAME",
            "relay-abc._domainkey.mail.relay.example.com.",
        )
        dns_resolver.add(domain.dmarc_record_name, "TXT", "v=DMARC1; p=none")
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/verify"
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/domains/{domain.pk}/")

    def test_post__not_found_for_other_org(self, admin_client, org, write_org):
        domain = Domain.objects.create(name="other.com", org=write_org)
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/verify"
        )
        assert response.status_code == 404
