import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from domains.models import Domain
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport


def make_report(org, **kwargs):
    defaults = {
        "org": org,
        "mail_from": "feedback@gmail.com",
        "rcpt_to": "fbl@acme.com",
        "reporting_org": "gmail",
        "feedback_type": "abuse",
        "original_mail_from": "sender@acme.com",
    }
    return FblReport.objects.create(**(defaults | kwargs))


def overview_url(org):
    return reverse("reputation:overview", kwargs={"org_slug": org.slug})


@pytest.mark.django_db
class TestFblReportListView:
    def test_get__lists_fbl_reports(self, admin_client, org):
        make_report(org)
        response = admin_client.get(
            reverse("reputation:fbl-report-list", kwargs={"org_slug": org.slug})
        )
        assert response.status_code == 200
        assert b"sender@acme.com" in response.content

    def test_get__filters_by_domain(self, admin_client, org):
        acme = Domain.objects.create(name="acme.com", org=org)
        globex = Domain.objects.create(name="globex.com", org=org)
        make_report(org, domain=acme, original_mail_from="one@acme.com")
        make_report(org, domain=globex, original_mail_from="two@globex.com")
        response = admin_client.get(
            reverse("reputation:fbl-report-list", kwargs={"org_slug": org.slug}),
            {"domain": "globex.com"},
        )
        assert response.status_code == 200
        assert b"two@globex.com" in response.content
        assert b"one@acme.com" not in response.content

    def test_get__filters_by_feedback_type(self, admin_client, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        make_report(
            org,
            domain=domain,
            feedback_type="abuse",
            original_mail_from="abuse@acme.com",
        )
        make_report(
            org,
            domain=domain,
            feedback_type="fraud",
            original_mail_from="fraud@acme.com",
        )
        response = admin_client.get(
            reverse("reputation:fbl-report-list", kwargs={"org_slug": org.slug}),
            {"feedback_type": "fraud"},
        )
        assert response.status_code == 200
        assert b"fraud@acme.com" in response.content
        assert b"abuse@acme.com" not in response.content


@pytest.mark.django_db
class TestFblReportDetailView:
    def make_report_with_body(self, org, body: bytes):
        message = IncomingMessage.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
            raw_body=SimpleUploadedFile("report.eml", body),
        )
        return FblReport.objects.create(
            org=org,
            message=message,
            reporting_org="gmail",
            arrival_at=timezone.now(),
            original_mail_from="sender@acme.com",
        )

    def test_get__shows_report_headers_and_body(self, admin_client, org):
        report = self.make_report_with_body(
            org,
            b"From: feedback@gmail.com\r\n"
            b"Subject: Complaint\r\n\r\n"
            b"User marked the message as spam.",
        )
        response = admin_client.get(
            reverse(
                "reputation:fbl-report-detail",
                kwargs={"org_slug": org.slug, "pk": report.pk},
            )
        )
        assert response.status_code == 200
        assert ("From", "feedback@gmail.com") in response.context["headers"]
        assert "User marked the message as spam." in response.context["body"]

    def test_get__shows_report_without_body(self, admin_client, org):
        report = self.make_report_with_body(org, b"")
        response = admin_client.get(
            reverse(
                "reputation:fbl-report-detail",
                kwargs={"org_slug": org.slug, "pk": report.pk},
            )
        )
        assert response.status_code == 200
        assert response.context["body"] == ""


@pytest.mark.django_db
class TestReputationOverviewView:
    def test_get__shows_overview(self, admin_client, org):
        response = admin_client.get(overview_url(org))
        assert response.status_code == 200
        assert response.context["stats"]["total_sent"] == 0

    def test_get__counts_held_spam_as_complaints_in_chart(
        self, admin_client, org, user
    ):
        domain = Domain.objects.create(name="acme.com", org=org)
        OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            domain=domain,
            status=OutgoingMessage.Status.HELD,
            raw_body=SimpleUploadedFile("held.eml", b"body"),
        )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        assert any(row["complained"] == 1 for row in response.context["chart"]["rows"])
