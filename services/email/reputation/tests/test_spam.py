from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import Organization
from domains.models import Domain
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.msa.tasks import check_outgoing_spam
from services.email.mta.models import IncomingMessage
from services.email.mta.tasks import check_incoming_spam
from services.email.reputation.charts import build_reputation_chart
from services.email.reputation.evaluation import (
    check_org_reputation,
    compute_org_reputation,
)
from services.email.reputation.models import FblReport
from services.email.spam import SpamAction, SpamResult


@pytest.mark.django_db
class TestComputeOrgReputation:
    def test_compute_org_reputation__counts_held_spam_as_complaints(self, org, user):
        domain = Domain.objects.create(name="acme.com", org=org)
        for _ in range(3):
            OutgoingMessage.objects.create(
                org=org,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                domain=domain,
                status=OutgoingMessage.Status.HELD,
                raw_body=SimpleUploadedFile("test.eml", b"x"),
            )

        stats = compute_org_reputation(org)
        assert stats["complaints"] == 3
        assert stats["total_sent"] == 3

    def test_compute_org_reputation__counts_provider_fbl_as_complaint(self, org, user):
        OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        message = IncomingMessage.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="postmaster@acme.com",
        )
        FblReport.objects.create(
            org=org,
            message=message,
            original_mail_from="sender@acme.com",
            source=FblReport.Source.PROVIDER,
        )

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 1

    def test_compute_org_reputation__ignores_relay_generated_fbl(self, org, user):
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        FblReport.objects.create(
            org=org,
            message=message,
            original_mail_from="sender@acme.com",
            source=FblReport.Source.RELAY,
        )

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 0

    def test_compute_org_reputation__held_message_not_double_counted_by_fbl(
        self, org, user
    ):
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.HELD,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        FblReport.create_for_spam(message)

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 1


@pytest.mark.django_db
class TestCheckOrgReputation:
    def test_check_org_reputation__locks_on_threshold_breach(
        self, org, user, mailoutbox, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
        )

        check_org_reputation(org)

        org.refresh_from_db()
        assert org.suspended_at is not None
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["alice@example.com"]

    def test_check_org_reputation__ignores_soft_bounces(self, org, user, settings):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=450,
        )

        check_org_reputation(org)

        org.refresh_from_db()
        assert org.suspended_at is None

    def test_check_org_reputation__skips_notification_when_already_locked(
        self, org, user, mailoutbox, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        Organization.objects.filter(pk=org.pk).update(suspended_at=timezone.now())
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
        )

        check_org_reputation(org)

        org.refresh_from_db()
        assert org.suspended_at is not None
        assert len(mailoutbox) == 0


def make_sent_message(org):
    return OutgoingMessage.objects.create(
        org=org,
        mail_from="sender@acme.com",
        rcpt_to="rcpt@example.com",
        status=OutgoingMessage.Status.SENT,
        raw_body=SimpleUploadedFile("test.eml", b"x"),
    )


class TestCheckReputationOnHardBounce:
    @pytest.mark.django_db
    def test_check_reputation_on_hard_bounce__locks(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = make_sent_message(org)

        with django_capture_on_commit_callbacks(execute=True):
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.BOUNCED,
                code=550,
            )

        org.refresh_from_db()
        assert org.suspended_at is not None

    @pytest.mark.django_db
    def test_check_reputation_on_hard_bounce__ignores_soft_bounce(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = make_sent_message(org)

        with django_capture_on_commit_callbacks(execute=True):
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.BOUNCED,
                code=450,
            )

        org.refresh_from_db()
        assert org.suspended_at is None


class TestCheckReputationOnHeldMessage:
    @pytest.mark.django_db
    def test_check_reputation_on_held_message__locks(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.PENDING,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )

        with django_capture_on_commit_callbacks(execute=True):
            message.status = OutgoingMessage.Status.HELD
            message.save(update_fields=["status"])

        org.refresh_from_db()
        assert org.suspended_at is not None

    @pytest.mark.django_db
    def test_check_reputation_on_held_message__ignores_regular_send(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1

        with django_capture_on_commit_callbacks(execute=True):
            make_sent_message(org)

        org.refresh_from_db()
        assert org.suspended_at is None

    @pytest.mark.django_db
    def test_check_reputation_on_held_message__creates_relay_fbl_report(
        self, org, user, mailoutbox, settings
    ):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            domain=domain,
            status=OutgoingMessage.Status.PENDING,
            raw_body=SimpleUploadedFile("test.eml", b"spam body"),
        )

        message.status = OutgoingMessage.Status.HELD
        message.save(update_fields=["status"])

        report = FblReport.objects.get(org=org)
        assert report.source == FblReport.Source.RELAY
        assert report.original_rcpt_to == "rcpt@example.com"
        assert report.message_id == message.pk
        assert len(mailoutbox) == 0

    @pytest.mark.django_db(transaction=True)
    def test_check_reputation_on_held_message__creates_relay_fbl_report_for_outgoing_spam(
        self, org, user
    ):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="bob@example.com, carol@example.com",
            domain=domain,
            status=OutgoingMessage.Status.PENDING,
            raw_body=SimpleUploadedFile("test.eml", b"spam body"),
        )

        with patch(
            "services.email.msa.tasks.check_message",
            return_value=SpamResult(score=10.0, action=SpamAction.REJECT),
        ):
            check_outgoing_spam.func(message_pk=str(message.pk), client_ip="1.2.3.4")

        report = FblReport.objects.get(org=org)
        assert report.source == FblReport.Source.RELAY
        assert report.original_rcpt_to == "bob@example.com"


class TestCheckReputationOnIncomingMessage:
    @pytest.mark.django_db(transaction=True)
    def test_check_reputation_on_incoming_message__creates_relay_fbl_report(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        message = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="example.com",
            mail_from="spam@acme.com",
            rcpt_to="inbox@example.com",
            raw_body=SimpleUploadedFile("test.eml", b"spam body"),
        )

        with patch(
            "services.email.mta.tasks.check_message",
            return_value=SpamResult(score=20.0, action=SpamAction.REJECT),
        ):
            check_incoming_spam.func(message_pk=str(message.pk), client_ip="")

        report = FblReport.objects.get(org=org)
        assert report.source == FblReport.Source.RELAY
        assert report.domain == domain
        assert report.message_id == message.pk


@pytest.mark.django_db
class TestBuildReputationChart:
    def test_build_reputation_chart__matches_evaluation_complaint_semantics(
        self, org, user, settings
    ):
        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage.objects.create(
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            domain=domain,
            status=OutgoingMessage.Status.HELD,
            raw_body=SimpleUploadedFile("test.eml", b"x"),
        )
        FblReport.create_for_spam(message)
        report_email = IncomingMessage.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="postmaster@acme.com",
        )
        FblReport.objects.create(
            org=org,
            message=report_email,
            original_mail_from="sender@acme.com",
        )

        rows = build_reputation_chart(org)["rows"]

        assert rows[-1]["complained"] == 2
        assert compute_org_reputation(org)["complaints"] == 2
