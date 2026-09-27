import pytest
from django.urls import reverse

from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcRecord, DmarcReport
from services.email.msa.models import MsaCredential, OutgoingMessage
from services.email.mta.models import IncomingMessage, TlsReport
from services.email.reputation.models import FblReport


def connect_app(org):
    """Create an SMTP credential and authenticate with it once."""
    credential, raw_key = MsaCredential.objects.create_with_key(
        org=org, name="test app"
    )
    credential.verify_key(raw_key)
    return credential


def complete_onboarding(org):
    """Send a message and connect an app, which is all the checklist asks for."""
    OutgoingMessage.objects.create(
        org=org,
        rcpt_to="x@example.com",
        mail_from="y@example.com",
        domain=Domain.objects.get(org=org, is_managed=True),
    )
    connect_app(org)


@pytest.mark.django_db
class TestGetStartedView:
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

    def test_get__shows_first_steps(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["has_outgoing_message"] is False
        assert response.context["connected_credential"] is None

    def test_get__shows_connected_app_step(self, admin_client, org, user):
        connect_app(org)
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["connected_credential"] is not None
        assert response.context["has_outgoing_message"] is False

    def test_get__unused_credential_is_not_a_connected_app(self, admin_client, org):
        MsaCredential.objects.create_with_key(org=org, name="unused")
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["connected_credential"] is None

    def test_get__creates_a_credential_from_the_step_dialog(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        content = response.content.decode()
        assert (
            f'action="{reverse("msa:credential-create", kwargs={"org_slug": org.slug})}"'
            in content
        )
        assert 'id="dlg-new-credential"' in content
        assert (
            'data-dialog="dlg-new-credential"'
            in content.split('id="dlg-new-credential"', 1)[0]
        )

    def test_get__step_dialog_creates_a_sandbox_credential(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        content = response.content.decode()
        assert '<input type="hidden" name="sandbox" value="true">' in content
        assert 'id="id_sandbox"' not in content

    def test_get__connected_app_links_to_the_credentials_page(self, admin_client, org):
        connect_app(org)
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse("msa:credential-list", kwargs={"org_slug": org.slug}) in content
        assert 'data-dialog="dlg-new-credential"' not in content

    def test_get__submission_values_use_the_configured_host(
        self, admin_client, org, settings
    ):
        """The configured host wins over the `testserver` host the client sends."""
        settings.RELAY_SMTP_PUBLIC_HOSTNAME = "smtp.relay.example"
        session = admin_client.session
        session["raw_key"] = "abcdefghijklmnop"
        session.save()

        response = admin_client.get(f"/org/{org.slug}/email/")

        assert response.status_code == 200
        assert response.context["smtp_hostname"] == "smtp.relay.example"
        assert "smtp.relay.example" in response.content.decode()

    def test_get__hides_the_values_until_a_key_is_pending(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")

        content = response.content.decode()
        assert 'id="dlg-credential-key"' not in content
        assert 'class="accordion"' not in content
        assert "<table" not in content

    def test_get__key_dialog_carries_the_connection_values(self, admin_client, org):
        session = admin_client.session
        session["raw_key"] = "abcdefghijklmnop"
        session.save()

        response = admin_client.get(f"/org/{org.slug}/email/")

        content = response.content.decode()
        assert content.index('id="dlg-credential-key"') < content.index(
            'class="accordion"'
        )
        assert content.index('class="accordion"') < content.index("<table")

    def test_post__credential_dialog_opens_on_this_page(self, admin_client, org):
        """Creating from the step keeps the member on the page, dialog open."""
        create = admin_client.post(
            reverse("msa:credential-create", kwargs={"org_slug": org.slug}),
            {
                "name": "Onboarding app",
                "sandbox": "true",
                "next": f"/org/{org.slug}/email/",
            },
        )
        assert create.status_code == 302
        assert create.url == f"/org/{org.slug}/email/"

        response = admin_client.get(create.url)

        assert response.status_code == 200
        assert 'id="dlg-credential-key"' in response.content.decode()
        assert MsaCredential.objects.get(org=org).type == MsaCredential.Type.SANDBOX

    def test_get__shows_sent_first_email_step(self, admin_client, org, user):
        OutgoingMessage.objects.create(
            org=org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
            domain=Domain.objects.get(org=org, is_managed=True),
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["has_outgoing_message"] is True
        assert response.context["connected_credential"] is None

    def test_get__completes_without_a_custom_domain(self, admin_client, org):
        """A domain you own is not part of the checklist, so it cannot hold it open."""
        complete_onboarding(org)
        assert not Domain.objects.filter(org=org, is_managed=False).exists()

        response = admin_client.get(f"/org/{org.slug}/email/")

        assert response.status_code == 302
        assert response.url == reverse(
            "monitoring:overview", kwargs={"org_slug": org.slug}
        )

    def test_get__redirects_to_reputation_when_onboarding_is_complete(
        self, admin_client, org, user
    ):
        complete_onboarding(org)
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 302
        assert response.url == reverse(
            "monitoring:overview", kwargs={"org_slug": org.slug}
        )

    def test_get__renders_dialog_with_header_trigger(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="dlg-test-email"' in content
        assert (
            f'action="{reverse("msa:message-test", kwargs={"org_slug": org.slug})}"'
            in content
        )
        assert (
            'data-dialog="dlg-test-email"' in content.split('id="dlg-test-email"', 1)[0]
        )

    def test_get__first_steps_scoped_to_org(self, admin_client, org, write_org, user):
        domain = Domain.objects.get(org=write_org, is_managed=True)
        Domain.objects.create(name="other.com", org=write_org)
        OutgoingMessage.objects.create(
            org=write_org,
            rcpt_to="x@example.com",
            mail_from="y@example.com",
            domain=domain,
        )
        response = admin_client.get(f"/org/{org.slug}/email/")
        assert response.status_code == 200
        assert response.context["has_outgoing_message"] is False
        assert response.context["connected_credential"] is None


@pytest.mark.django_db
class TestOnboardingNavigation:
    def test_get__sidebar_links_get_started_while_onboarding_is_incomplete(
        self, admin_client, org
    ):
        response = admin_client.get(f"/org/{org.slug}/email/reports/")
        assert response.status_code == 200
        assert f'href="/org/{org.slug}/email/"' in response.content.decode()

    def test_get__sidebar_drops_get_started_when_onboarding_is_complete(
        self, admin_client, org, user
    ):
        complete_onboarding(org)
        response = admin_client.get(f"/org/{org.slug}/email/reports/")
        assert response.status_code == 200
        content = response.content.decode()
        assert ">Get started</span>" not in content
        assert f'href="/org/{org.slug}/email/monitoring/"' in content


@pytest.mark.django_db
class TestReportListView:
    @pytest.fixture
    def domain(self, org):
        return Domain.objects.create(name="acme.com", org=org)

    @pytest.fixture
    def dmarc_report(self, org, domain):
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
        return DmarcFailureReport.objects.create(
            org=org,
            domain=domain,
            mail_from="ruf@gmail.com",
            rcpt_to="ruf@acme.com",
            source_ip_address="10.0.0.2",
        )

    @pytest.fixture
    def tls_report(self, org, domain):
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
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="feedback@gmail.com",
            rcpt_to="postmaster@acme.com",
        )
        return FblReport.objects.create(
            org=org,
            domain=domain,
            message=message,
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

    def test_get__dmarc_type_shows_chart(self, admin_client, org, dmarc_report):
        response = admin_client.get(f"/org/{org.slug}/email/reports/")

        assert response.status_code == 200
        assert "series" in response.context["chart"]

    def test_get__tls_type_shows_chart(self, admin_client, org, tls_report):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=tls")

        assert response.status_code == 200
        assert "series" in response.context["chart"]

    def test_get__fbl_type_has_no_chart(self, admin_client, org, fbl_report):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=fbl")

        assert response.status_code == 200
        assert response.context["chart"] is None

    def test_get__fbl_type_renders_no_chart_card(self, admin_client, org, fbl_report):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=fbl")

        assert response.status_code == 200
        assert "chart-reports" not in response.content.decode()

    def test_get__names_the_filter_values_in_the_trigger(
        self, admin_client, org, tls_report
    ):
        response = admin_client.get(
            f"/org/{org.slug}/email/reports/?type=tls&domain=acme.com"
        )

        assert response.status_code == 200
        trigger = (
            response.content.decode()
            .split('id="report-filters-trigger"', 1)[1]
            .split("</button>", 1)[0]
        )
        assert "acme.com" in trigger

    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/reports/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/reports/")
        assert response.status_code == 404
