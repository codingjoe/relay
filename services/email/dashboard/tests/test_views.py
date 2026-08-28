import pytest

from domains.models import Domain
from services.email.msa.models import OutgoingMessage
from services.email.reputation.models import FblReport


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


@pytest.mark.django_db
class TestChartDataView:
    @pytest.mark.parametrize(
        "chart_type",
        ["outgoing", "incoming", "dmarc", "tls", "reputation"],
    )
    def test_get__returns_chart_data(self, admin_client, org, chart_type):
        response = admin_client.get(f"/org/{org.slug}/email/api/charts/{chart_type}/")
        assert response.status_code == 200
        assert "series" in response.json()
        assert "rows" in response.json()

    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/api/charts/outgoing/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/api/charts/outgoing/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestReportListView:
    @pytest.fixture
    def domain(self, org):
        return Domain.objects.create(name="acme.com", org=org)

    @pytest.fixture
    def dmarc_report(self, org, domain):
        from services.email.dmarc.models import DmarcRecord, DmarcReport

        report = DmarcReport.objects.create(
            org=org,
            domain=domain,
            mail_from="dmarc@gmail.com",
            rcpt_to="dmarc@acme.com",
            report_id="agg-1",
        )
        DmarcRecord.objects.create(
            report=report,
            source_ip_address="10.0.0.1",
        )
        return report

    @pytest.fixture
    def failure_report(self, org, domain):
        from services.email.dmarc.models import DmarcFailureReport

        return DmarcFailureReport.objects.create(
            org=org,
            domain=domain,
            mail_from="ruf@gmail.com",
            rcpt_to="ruf@acme.com",
            source_ip_address="10.0.0.2",
        )

    @pytest.fixture
    def tls_report(self, org, domain):
        from services.email.mta.models import TlsReport

        return TlsReport.objects.create(
            org=org,
            domain=domain,
            mail_from="tlsrpt@gmail.com",
            rcpt_to="tlsrpt@acme.com",
            receiving_domain="acme.com",
            report_id="tls-1",
        )

    @pytest.fixture
    def fbl_report(self, org, domain):
        return FblReport.objects.create(
            org=org,
            domain=domain,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
            source_ip_address="10.0.0.3",
        )

    def test_get__fbl_type_lists_fbl_reports(
        self, admin_client, org, dmarc_report, fbl_report
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=fbl")

        assert response.status_code == 200
        assert list(response.context["reports"]) == [fbl_report]

    def test_get__dmarc_type_lists_dmarc_reports(
        self, admin_client, org, dmarc_report, tls_report
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/")

        assert response.status_code == 200
        assert list(response.context["reports"]) == [dmarc_report]

    def test_get__dmarc_type_filters_by_ip(
        self, admin_client, org, dmarc_report, tls_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=dmarc&ip=10.0.0.1"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [dmarc_report]

    def test_get__dmarc_type_ip_filter_excludes_other_ips(
        self, admin_client, org, dmarc_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=dmarc&ip=10.9.9.9"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == []

    def test_get__dmarc_type_ip_filter_requires_record_match(
        self, admin_client, org, dmarc_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=dmarc&ip=10.0.0.1"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [dmarc_report]

    def test_get__failures_type_lists_failure_reports(
        self, admin_client, org, failure_report, dmarc_report
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=failures")

        assert response.status_code == 200
        assert list(response.context["reports"]) == [failure_report]

    def test_get__failures_type_filters_by_ip(self, admin_client, org, failure_report):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=failures&ip=10.0.0.2"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [failure_report]

    def test_get__tls_type_lists_tls_reports(
        self, admin_client, org, tls_report, dmarc_report
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=tls")

        assert response.status_code == 200
        assert list(response.context["reports"]) == [tls_report]

    def test_get__tls_type_filters_by_domain(
        self, admin_client, org, tls_report, dmarc_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=tls&domain=acme.com"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [tls_report]

    def test_get__tls_type_domain_filter_excludes_other_domains(
        self, admin_client, org, tls_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=tls&domain=other.com"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == []

    def test_get__fbl_type_filters_by_domain(self, admin_client, org, fbl_report):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=fbl&domain=acme.com"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [fbl_report]

    def test_get__fbl_type_filters_by_ip(self, admin_client, org, fbl_report):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=fbl&ip=10.0.0.3"
        )

        assert response.status_code == 200
        assert list(response.context["reports"]) == [fbl_report]

    def test_get__unknown_type_falls_back_to_dmarc(
        self, admin_client, org, dmarc_report, fbl_report
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=bogus")

        assert response.status_code == 200
        assert list(response.context["reports"]) == [dmarc_report]

    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/reports/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/reports/")
        assert response.status_code == 404
