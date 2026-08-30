import pytest
from django.conf import settings
from django.contrib.messages import get_messages

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
        Domain.objects.create(name="acme.com", org=org)
        Domain.objects.create(name="other.com", org=write_org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/")
        assert response.status_code == 200
        domains = list(response.context["domains"])
        assert len(domains) == 2
        domain_names = {d.name for d in domains}
        assert domain_names == {
            "acme.com",
            f"{org.slug}.{settings.RELAY_MANAGED_SENDER_DOMAIN}",
        }

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

    def test_post__rejects_dot(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new", {"name": "."}
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/domains/")
        assert not Domain.objects.filter(name=".")

    def test_post__rejects_single_label(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new", {"name": "example"}
        )
        assert response.status_code == 302
        assert not Domain.objects.filter(name="example")

    def test_post__rejects_domain_overlapping_other_org(
        self,
        admin_client,
        org,
        write_org,
    ):
        Domain.objects.create(name="example.com", org=write_org)

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new",
            {"name": "app.example.com"},
        )

        assert response.status_code == 302
        assert not Domain.objects.filter(name="app.example.com").exists()
        assert any(
            "overlaps with a domain owned by another organization" in str(message)
            for message in get_messages(response.wsgi_request)
        )


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
        assert "dkim_cnames" in response.context

    def test_get__warns_about_apex_ns_delegation(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert b"apex delegation replaces the current DNS service" in response.content
        assert (
            b"Websites and other services on this domain will stop" in response.content
        )

    def test_get__groups_sending_and_receiving_records(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Sending records" in response.content
        assert b"Receiving records" in response.content
        assert f"10 {domain.sender_domain}.".encode() in response.content

    def test_get__not_found_for_managed_domain(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert response.status_code == 404

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        domain = Domain.objects.create(name="other.com", org=write_org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainVerifyView:
    def test_post__redirects_to_detail(self, admin_client, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        for cname_name, _ in domain.dkim_cnames:
            dns_resolver.add(
                cname_name,
                "CNAME",
                "relay-abc._domainkey.mail.relay.example.com.",
            )
        dns_resolver.add(domain.dmarc_record_name, "TXT", "v=DMARC1; p=none")
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", "v=STSv1; id=test")
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1; rua=mailto:{domain.tls_reporting_address}"',
        )
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

    def test_post__not_found_for_managed_domain(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/verify"
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainDeleteView:
    def test_post__deletes_custom_domain(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/delete"
        )

        assert response.status_code == 302
        assert not Domain.objects.filter(pk=domain.pk).exists()

    def test_post__does_not_delete_managed_domain(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/delete"
        )

        assert response.status_code == 404
        assert Domain.objects.filter(pk=domain.pk).exists()


@pytest.mark.django_db
class TestMtaStsPolicyView:
    def test_get__serves_policy_for_known_domain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "version: STSv1" in body
        assert "mode:" in body
        assert "mx: mail.relay.example.com" in body
        assert "max_age:" in body

    def test_get__returns_421_for_unknown_domain(self, client):
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.unknown.com"
        )
        assert response.status_code == 421

    def test_get__content_type_is_text_plain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response["Content-Type"] == "text/plain"

    def test_get__cache_control_header(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert "Cache-Control" in response
        assert "max-age=" in response["Cache-Control"]

    def test_get__serves_policy_for_subdomain_of_user_domain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.app.example.com"
        )
        assert response.status_code == 200
        assert "mx: mail.relay.example.com" in response.content.decode()

    def test_get__selects_most_specific_domain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        Domain.objects.create(name="app.example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.app.example.com"
        )
        assert response.status_code == 200
        assert "mx: mail.relay.app.example.com" in response.content.decode()

    def test_get__handles_uppercase_mta_sts_prefix(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="MTA-STS.example.com"
        )
        assert response.status_code == 200
        assert "version: STSv1" in response.content.decode()

    def test_get__vary_host_header(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response["Vary"] == "Host"
