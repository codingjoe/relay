import pytest
from django.conf import settings
from django.contrib.messages import get_messages

from domains.models import Domain

QUICK_START_FIELDS = ("nameserver", "spf", "dkim_rsa2048")
SENDING_FIELDS = (*QUICK_START_FIELDS, "dkim_ed25519")
RECEIVING_FIELDS = ("mx",)
REPORTING_FIELDS = ("dmarc", "mta_sts", "tls_rpt")
ALL_CHECK_FIELDS = (*SENDING_FIELDS, *RECEIVING_FIELDS, *REPORTING_FIELDS)


def publish_dns_records(dns_resolver, domain, fields):
    """Register the DNS records that make *fields* pass their check."""
    for field in fields:
        match field:
            case "nameserver":
                dns_resolver.add(
                    domain.sender_domain,
                    "NS",
                    *(f"{nameserver}." for nameserver in settings.DNS_NS_NAMESERVERS),
                )
            case "spf":
                dns_resolver.add(
                    domain.name,
                    "TXT",
                    f"v=spf1 include:{domain.sender_domain} ~all",
                )
            case "dkim_rsa2048" | "dkim_ed25519":
                name, target = domain.dkim_cnames[field]
                dns_resolver.add(name, "CNAME", f"{target}.")
            case "dmarc":
                dns_resolver.add(
                    domain.dmarc_record_name, "TXT", f'"{domain.dmarc_record}"'
                )
            case "mx":
                dns_resolver.add(
                    domain.name,
                    "MX",
                    *(f"10 {hostname}." for hostname in settings.DNS_MX_HOSTNAMES),
                )
            case "mta_sts":
                dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=test"')
                dns_resolver.add(
                    f"mta-sts.{domain.name}",
                    "CNAME",
                    f"mta-sts.{domain.sender_domain}.",
                )
            case "tls_rpt":
                dns_resolver.add(
                    f"_smtp._tls.{domain.name}",
                    "TXT",
                    f'"v=TLSRPTv1;rua=mailto:{domain.tls_reporting_address}"',
                )


def verify_dns(client, org, domain, dns_resolver, fields):
    """Publish *fields*, click verify, and return the level and text of every message."""
    publish_dns_records(dns_resolver, domain, fields)
    response = client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")
    assert response.status_code == 302
    return [
        (message.level_tag, str(message))
        for message in get_messages(response.wsgi_request)
    ]


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
            f"{org.slug}.{settings.MANAGED_SENDER_DOMAIN}",
        }

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/domains/")
        assert response.status_code == 404

    def test_get__renders_empty_state_without_domains(self, admin_client, org):
        Domain.objects.filter(org=org).delete()

        response = admin_client.get(f"/org/{org.slug}/email/domains/")

        assert response.status_code == 200
        assert b"No domains yet." in response.content
        assert b"the first send needs no" in response.content
        assert b"Add Domain" in response.content

    def test_get__cache_control_header(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/domains/")

        assert (
            response.headers["Cache-Control"] == "private, max-age=5, must-revalidate"
        )
        assert "ETag" in response.headers
        assert "Last-Modified" in response.headers

    def test_get__not_modified_when_etag_matches(self, admin_client, org):
        url = f"/org/{org.slug}/email/domains/"
        etag = admin_client.get(url).headers["ETag"]

        response = admin_client.get(url, headers={"If-None-Match": etag})

        assert response.status_code == 304

    def test_get__fresh_response_after_a_release(self, admin_client, org, settings):
        url = f"/org/{org.slug}/email/domains/"
        etag = admin_client.get(url).headers["ETag"]

        settings.SENTRY_RELEASE = "sha-next"

        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 200
        assert response.headers["ETag"] != etag

    def test_get__keeps_the_cached_policy_when_not_modified(self, admin_client, org):
        url = f"/org/{org.slug}/email/domains/"
        etag = admin_client.get(url).headers["ETag"]

        response = admin_client.get(url, headers={"If-None-Match": etag})

        assert response.status_code == 304
        assert "Content-Security-Policy" not in response.headers

    def test_get__fresh_response_when_domain_added(self, admin_client, org):
        url = f"/org/{org.slug}/email/domains/"
        etag = admin_client.get(url).headers["ETag"]

        Domain.objects.create(name="new.example.com", org=org)

        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 200
        assert response.headers["ETag"] != etag


@pytest.mark.django_db
class TestDomainCreateView:
    def test_post__creates_domain(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new", {"name": "new.com"}
        )
        assert response.status_code == 302
        domain = Domain.objects.get(name="new.com")
        assert domain.org == org

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

    def test_post__rejects_platform_domain(self, admin_client, org, settings):
        settings.PLATFORM_DOMAIN = "relay.example.com"
        settings.MANAGED_SENDER_DOMAIN = "open.relay.example.com"

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/new",
            {"name": "relay.example.com"},
        )

        assert response.status_code == 302
        assert not Domain.objects.filter(name="relay.example.com").exists()


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

    def test_get__cache_control_header(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert (
            response.headers["Cache-Control"] == "private, max-age=5, must-revalidate"
        )
        assert "ETag" in response.headers

    def test_post__updates_mta_sts_mx_hosts(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/",
            {
                "mta_sts_mx_hostnames": (
                    "MX1.Other.com.\nmx1.other.com\n*.MX2.Other.com."
                )
            },
        )

        assert response.status_code == 302
        domain.refresh_from_db()
        assert domain.mta_sts_mx_hostnames == ["mx1.other.com", "*.mx2.other.com"]

    def test_post__rejects_invalid_mta_sts_mx_hostname(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/",
            {"mta_sts_mx_hostnames": "mx*.other.com"},
        )

        assert response.status_code == 200
        assert b"Enter a valid domain name" in response.content
        domain.refresh_from_db()
        assert domain.mta_sts_mx_hostnames == []

    def test_get__not_modified_when_etag_matches(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        url = f"/org/{org.slug}/email/domains/{domain.pk}/"
        etag = admin_client.get(url).headers["ETag"]

        response = admin_client.get(url, headers={"If-None-Match": etag})

        assert response.status_code == 304

    def test_get__fresh_response_after_a_release(self, admin_client, org, settings):
        domain = Domain.objects.create(name="example.com", org=org)
        url = f"/org/{org.slug}/email/domains/{domain.pk}/"
        etag = admin_client.get(url).headers["ETag"]

        settings.SENTRY_RELEASE = "sha-next"

        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 200
        assert response.headers["ETag"] != etag

    def test_get__fresh_response_when_verification_changes_status(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        url = f"/org/{org.slug}/email/domains/{domain.pk}/"
        etag = admin_client.get(url).headers["ETag"]

        verify_dns(admin_client, org, domain, dns_resolver, ALL_CHECK_FIELDS)

        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 200
        assert response.headers["ETag"] != etag

    def test_get__groups_records_into_one_tab_per_purpose(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        content = response.content.decode()

        assert 'id="domain-dns-tab-sending"' in content
        assert 'id="domain-dns-tab-receiving"' in content
        assert 'id="domain-dns-tab-reporting"' in content
        prerequisite = content.split('role="tabpanel"')[0]
        for ns in response.context["nameservers"]:
            assert f'value="{ns}."' in prerequisite
        for mx_hostname in settings.DNS_MX_HOSTNAMES:
            assert f'value="{mx_hostname}."' in content

    def test_get__offers_a_zone_file_for_each_group(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        content = response.content.decode()
        for group in ("delegation", "sending", "receiving", "reporting"):
            assert (
                f"/org/{org.slug}/email/domains/{domain.pk}/zonefile/{group}" in content
            )

    def test_get__renders_each_record_group_in_its_own_tab(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        verify_dns(admin_client, org, domain, dns_resolver, ALL_CHECK_FIELDS)

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        content = response.content.decode()
        sending, receiving, reporting = content.split('role="tabpanel"')[1:]

        tabs = {
            sending: (
                domain.root_spf_record,
                domain.dkim_cnames["dkim_rsa2048"][1],
                domain.dkim_cnames["dkim_ed25519"][1],
            ),
            receiving: (*(f"{hostname}." for hostname in settings.DNS_MX_HOSTNAMES),),
            reporting: (
                domain.dmarc_record,
                domain.mta_sts_record,
                domain.mta_sts_cname_target,
                domain.tls_rpt_record,
            ),
        }
        for tab, records in tabs.items():
            for record in records:
                assert record in tab
                assert sum(record in other for other in tabs) == 1

        prerequisite = content.split('role="tabpanel"')[0]
        for ns in response.context["nameservers"]:
            assert f'value="{ns}."' in prerequisite
            assert sum(f'value="{ns}."' in tab for tab in tabs) == 0

    def test_get__renders_passing_check_status(self, admin_client, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        publish_dns_records(dns_resolver, domain, ALL_CHECK_FIELDS)
        admin_client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Passing" in response.content
        assert b"Failing" not in response.content

    def test_get__renders_failing_check_status_and_error(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        admin_client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Failing" in response.content
        assert b"NS record not found or incorrect." in response.content

    def test_get__tab_status_names_every_group_ready(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        publish_dns_records(dns_resolver, domain, ALL_CHECK_FIELDS)
        admin_client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Sending" in response.content
        assert b"Receiving" in response.content
        assert b"Reporting" in response.content
        assert b"Delegate the sender subdomain" in response.content
        assert b"Not verified" not in response.content
        assert b"Not ready" not in response.content
        assert b"Not set up" not in response.content

    def test_get__tab_status_names_every_group_unpublished(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Sending" in response.content
        assert b"Receiving" in response.content
        assert b"Reporting" in response.content
        assert b"Delegate the sender subdomain" in response.content
        assert b"Not checked" in response.content
        assert response.content.count(b"Not set up") == 3

    def test_get__sending_tab_fails_while_a_record_is_missing(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        publish_dns_records(dns_resolver, domain, ("nameserver",))
        admin_client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Not verified" in response.content

    def test_get__reporting_tab_fails_while_a_record_is_missing(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)
        publish_dns_records(
            dns_resolver,
            domain,
            (*SENDING_FIELDS, *RECEIVING_FIELDS, "dmarc"),
        )
        admin_client.post(f"/org/{org.slug}/email/domains/{domain.pk}/verify")

        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert b"Not verified" in response.content

    def test_get__not_found_for_managed_domain(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")

        assert response.status_code == 404

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        domain = Domain.objects.create(name="other.com", org=write_org)
        response = admin_client.get(f"/org/{org.slug}/email/domains/{domain.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainZoneFileView:
    def zone_url(self, org, domain, group):
        return f"/org/{org.slug}/email/domains/{domain.pk}/zonefile/{group}"

    def test_get__requires_login(self, client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = client.get(self.zone_url(org, domain, "sending"))

        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__downloads_the_sending_zone_file(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(self.zone_url(org, domain, "sending"))

        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain; charset=utf-8"
        assert (
            response["Content-Disposition"]
            == 'attachment; filename="example.com-sending.zone"'
        )
        content = response.content.decode()
        assert "$ORIGIN example.com." in content
        assert f'@ IN TXT "{domain.root_spf_record}"' in content
        for name, target in domain.dkim_cnames.values():
            assert (
                f"{name.removesuffix(f'.{domain.name}')} IN CNAME {target}." in content
            )

    def test_get__delegation_zone_file_lists_the_nameservers(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(self.zone_url(org, domain, "delegation"))

        content = response.content.decode()
        assert "mail.relay IN NS " in content
        assert content.count("mail.relay IN NS ") == 2

    def test_get__receiving_zone_file_lists_the_mx_hosts(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(self.zone_url(org, domain, "receiving"))

        content = response.content.decode()
        for hostname in settings.DNS_MX_HOSTNAMES:
            assert f"@ IN MX 10 {hostname.split(':')[0]}." in content

    def test_get__reporting_zone_file_lists_the_records(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(self.zone_url(org, domain, "reporting"))

        content = response.content.decode()
        assert f'_dmarc IN TXT "{domain.dmarc_record}"' in content
        assert f'_mta-sts IN TXT "{domain.mta_sts_record}"' in content
        assert f"mta-sts IN CNAME {domain.mta_sts_cname_target}." in content
        assert f'_smtp._tls IN TXT "{domain.tls_rpt_record}"' in content

    def test_get__not_found_for_unknown_group(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)

        response = admin_client.get(self.zone_url(org, domain, "other"))

        assert response.status_code == 404

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        domain = Domain.objects.create(name="other.com", org=write_org)

        response = admin_client.get(self.zone_url(org, domain, "sending"))

        assert response.status_code == 404

    def test_get__not_found_for_managed_domain(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)

        response = admin_client.get(self.zone_url(org, domain, "sending"))

        assert response.status_code == 404


@pytest.mark.django_db
class TestDomainVerifyView:
    def test_post__redirects_to_detail(self, admin_client, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        publish_dns_records(dns_resolver, domain, ALL_CHECK_FIELDS)

        response = admin_client.post(
            f"/org/{org.slug}/email/domains/{domain.pk}/verify"
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/domains/{domain.pk}/")

    def test_post__nothing_published_reports_delegation_not_set_up(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(admin_client, org, domain, dns_resolver, ()) == [
            ("info", "delegation verification is not set up yet.")
        ]

    def test_post__delegation_published_reports_sending_not_set_up(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(admin_client, org, domain, dns_resolver, ("nameserver",)) == [
            ("info", "sending verification is not set up yet.")
        ]

    def test_post__sending_quick_start_reports_failing_count(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            QUICK_START_FIELDS,
        ) == [
            ("error", "sending verification failed: 1 of 3 checks are still failing.")
        ]

    def test_post__sending_published_reports_receiving_not_set_up(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            SENDING_FIELDS,
        ) == [("info", "receiving verification is not set up yet.")]

    def test_post__receiving_published_reports_reporting_not_set_up(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            (*SENDING_FIELDS, *RECEIVING_FIELDS),
        ) == [("info", "reporting verification is not set up yet.")]

    def test_post__reporting_nearly_ready_reports_failing_count(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            (*SENDING_FIELDS, *RECEIVING_FIELDS, "dmarc", "mta_sts"),
        ) == [
            (
                "error",
                "reporting verification failed: 1 of 3 checks are still failing.",
            )
        ]

    def test_post__receiving_missing_reports_receiving_not_set_up(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            (*SENDING_FIELDS, *REPORTING_FIELDS),
        ) == [("info", "receiving verification is not set up yet.")]

    def test_post__every_check_passes_reports_success(
        self, admin_client, org, dns_resolver
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        assert verify_dns(
            admin_client,
            org,
            domain,
            dns_resolver,
            ALL_CHECK_FIELDS,
        ) == [("success", "Verification passed: every check passes.")]

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
        assert f"mx: {settings.DNS_MX_HOSTNAMES[0]}" in body
        assert "max_age:" in body

    def test_get__serves_explicit_mx_hosts(self, client, org):
        Domain.objects.create(
            name="example.com",
            org=org,
            mta_sts_mx_hostnames=["mx1.other.com", "*.mx2.other.com"],
        )
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )

        body = response.content.decode()
        assert "mx: mx1.other.com" in body
        assert "mx: *.mx2.other.com" in body
        assert f"mx: {settings.DNS_MX_HOSTNAMES[0]}" not in body

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
        assert f"mx: {settings.DNS_MX_HOSTNAMES[0]}" in response.content.decode()

    def test_get__selects_most_specific_domain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        Domain.objects.create(name="app.example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.app.example.com"
        )
        assert response.status_code == 200
        assert f"mx: {settings.DNS_MX_HOSTNAMES[0]}" in response.content.decode()

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


class TestMtaStsAuthorizeView:
    @pytest.mark.django_db
    def test_get__ok_for_mta_sts_host(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": "mta-sts.example.com"}
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_get__ok_for_managed_domain(self, client, org):
        managed_name = f"{org.slug}.{settings.MANAGED_SENDER_DOMAIN}"
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": f"mta-sts.{managed_name}"}
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_get__forbidden_for_non_managed_platform_subdomain(self, client, org):
        # The row models a legacy claim that bypassed name validation, the
        # state the gate exists for.
        Domain.objects.bulk_create([Domain(name="foo.localhost", org=org)])
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": "mta-sts.foo.localhost"}
        )
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_get__forbidden_for_plain_subdomain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": "app.example.com"}
        )
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_get__forbidden_for_mta_sts_subdomain(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": "mta-sts.app.example.com"}
        )
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_get__forbidden_for_apex(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get("/internal/mta-sts/authorize/", {"domain": "example.com"})
        assert response.status_code == 403

    def test_get__forbidden_without_domain_parameter(self, client):
        response = client.get("/internal/mta-sts/authorize/")
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_get__forbidden_for_unknown_name(self, client):
        response = client.get(
            "/internal/mta-sts/authorize/", {"domain": "mta-sts.unknown.com"}
        )
        assert response.status_code == 403

    @pytest.mark.django_db
    @pytest.mark.parametrize("name", ["mta-sts.example.com", "mta-sts.unknown.com"])
    def test_get__no_store_cache_control_header(self, client, org, name):
        Domain.objects.create(name="example.com", org=org)
        response = client.get("/internal/mta-sts/authorize/", {"domain": name})
        assert response.headers["Cache-Control"] == "no-store"
