from datetime import datetime, time, timedelta

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage
from services.email.reputation.models import FblReport


def make_report(org, **kwargs):
    domain = kwargs.pop("domain", None) or Domain.objects.create(
        name="reports.test", org=org
    )
    message = IncomingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="feedback@gmail.com",
        rcpt_to="postmaster@acme.com",
    )
    defaults = {
        "org": org,
        "domain": domain,
        "message": message,
        "reporting_org": "gmail",
        "feedback_type": "abuse",
        "original_mail_from": "sender@acme.com",
    }
    return FblReport.objects.create(**(defaults | kwargs))


def overview_url(org):
    return reverse("reputation:overview", kwargs={"org_slug": org.slug})


def card_containing(content, label):
    """Return the markup of the card whose heading reads `label`."""
    heading = content.index(f">{label}<")
    return content[
        content.rindex("<section", 0, heading) : content.index("</section>", heading)
    ]


def last_month():
    """Return midday on the first day of the previous month."""
    first_of_this_month = timezone.localdate().replace(day=1)
    return timezone.make_aware(
        datetime.combine(first_of_this_month - timedelta(days=1), time(hour=12))
    )


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
        domain = Domain.objects.create(name="feedback.test", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
            raw_body=SimpleUploadedFile("report.eml", body),
        )
        return FblReport.objects.create(
            org=org,
            domain=domain,
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
        bounce_card = (
            response.content.decode()
            .split("Hard bounce rate", 1)[1]
            .split("Complaint rate", 1)[0]
        )
        assert "text-success" in bounce_card

    def test_get__tints_the_plan_card_when_suspended(self, admin_client, org):
        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at"])

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        assert "bg-destructive/10" in response.content.decode()

    def test_get__shows_the_free_plan(self, admin_client, org):
        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        assert (
            f"Up to {settings.RELAY_FREE_MONTHLY_MESSAGES:,} messages a month."
            in response.content.decode()
        )

    def test_get__charts_the_rates_as_shares_of_their_limits(
        self, admin_client, org, user
    ):
        domain = Domain.objects.create(name="acme.com", org=org)
        for index in range(2):
            message = OutgoingMessage.objects.create(
                org=org,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                domain=domain,
                raw_body=SimpleUploadedFile(f"{index}.eml", b"body"),
            )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        rates = response.context["chart_rates"]
        last = rates["rows"][-1]
        assert last["hard_bounce_rate"] == 50.0
        assert last["hard_bounce_share"] == 1000.0
        assert last["complaint_share"] == 0.0
        assert rates["threshold"]["value"] == 100

    def test_get__charts_this_month_and_last_month_volume(self, admin_client, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        for name, created_at in [("now.eml", None), ("then.eml", last_month())]:
            message = OutgoingMessage.objects.create(
                org=org,
                domain=domain,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                raw_body=SimpleUploadedFile(name, b"body"),
            )
            if created_at:
                OutgoingMessage.objects.filter(pk=message.pk).update(
                    created_at=created_at
                )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        chart = response.context["chart_volume"]
        this_month_cumulative = [
            row["this_month"] for row in chart["rows"] if row["this_month"] is not None
        ]
        last_month_cumulative = [
            row["last_month"] for row in chart["rows"] if row["last_month"] is not None
        ]
        assert this_month_cumulative[-1] == 1
        assert last_month_cumulative[-1] == 1
        assert chart["threshold"]["value"] == settings.RELAY_FREE_MONTHLY_MESSAGES
        assert "chart-volume" in response.content.decode()

    def test_get__tints_the_bounce_card_over_the_limit(self, admin_client, org, user):
        message = OutgoingMessage.objects.create(
            org=org,
            domain=Domain.objects.create(name="acme.com", org=org),
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            raw_body=SimpleUploadedFile("bounce.eml", b"body"),
        )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        content = response.content.decode()
        assert content.count("bg-destructive/10") == 1
        bounce_card = card_containing(content, "Hard bounce rate")
        assert "text-destructive" in bounce_card

    def test_get__tints_the_complaint_card_over_the_limit(
        self, admin_client, org, user
    ):
        OutgoingMessage.objects.create(
            org=org,
            domain=Domain.objects.create(name="acme.com", org=org),
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            raw_body=SimpleUploadedFile("held.eml", b"body"),
            status=OutgoingMessage.Status.HELD,
        )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        complaint_card = card_containing(response.content.decode(), "Complaint rate")
        assert "bg-destructive/10" in complaint_card
        assert "text-destructive" in complaint_card

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
        rows = response.context["chart_outcomes"]["rows"]
        assert any(row["complained"] == 100.0 for row in rows)

    def test_get__charts_every_day_as_a_share(self, admin_client, org, user):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            domain=domain,
            raw_body=SimpleUploadedFile("bounce.eml", b"body"),
        )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

        response = admin_client.get(overview_url(org))

        assert response.status_code == 200
        rows = response.context["chart_outcomes"]["rows"]
        day = [row for row in rows if row["total"]][-1]
        shares = [
            day[key]
            for key in ("delivered", "soft_bounced", "hard_bounced", "complained")
        ]
        assert day["hard_bounced"] == 100.0
        assert round(sum(shares), 1) == 100.0
