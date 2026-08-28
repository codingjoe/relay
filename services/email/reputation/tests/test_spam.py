import pytest

from services.email.reputation.models import FblReport


class TestFblReportCreateForSpam:
    def test_create_for_spam__returns_none_without_domain(self):
        from services.email.mta.models import IncomingMessage

        message = IncomingMessage(
            mail_from="spam@example.com",
            rcpt_to="rcpt@example.com",
        )
        result = FblReport.create_for_spam(message)
        assert result is None

    @pytest.mark.django_db
    def test_create_for_spam__creates_report_with_spam_fields(self, org, user):
        from django.core.files.base import ContentFile

        from domains.models import Domain
        from services.email.msa.models import OutgoingMessage

        domain = Domain.objects.create(name="acme.com", org=org)
        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            subject="Spam subject",
            message_id="<abc@acme.com>",
            domain=domain,
            status=OutgoingMessage.Status.HELD,
        )
        message.raw_body.save("test.eml", ContentFile(b"spam content"), save=False)
        message.save(force_insert=True)

        report = FblReport.create_for_spam(message)
        assert report is not None
        assert report.source == "relay"
        assert report.feedback_type == "abuse"
        assert report.user_agent == "relay"
        assert report.original_mail_from == "sender@acme.com"
        assert report.domain == domain
        assert report.org == org


@pytest.mark.django_db
class TestComputeOrgReputationSpamHeld:
    def test_compute_org_reputation__counts_held_spam_as_complaints(self, org, user):

        from django.core.files.base import ContentFile

        from domains.models import Domain
        from services.email.msa.models import OutgoingMessage
        from services.email.reputation.evaluation import compute_org_reputation

        domain = Domain.objects.create(name="acme.com", org=org)
        for _ in range(3):
            message = OutgoingMessage(
                sender=user,
                org=org,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                domain=domain,
                status=OutgoingMessage.Status.HELD,
            )
            message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
            message.save(force_insert=True)

        stats = compute_org_reputation(org)
        assert stats["complaints"] == 3
        assert stats["total_sent"] == 3


@pytest.mark.django_db
class TestCheckOrgReputationLock:
    def test_check_org_reputation__locks_on_threshold_breach(
        self, org, user, mailoutbox, settings
    ):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage, Transmission
        from services.email.reputation.evaluation import check_org_reputation

        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=550,
        )

        check_org_reputation(org)

        org.refresh_from_db()
        assert org.reputation_locked
        assert org.reputation_locked_at is not None
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["alice@example.com"]

    def test_check_org_reputation__ignores_soft_bounces(self, org, user, settings):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage, Transmission
        from services.email.reputation.evaluation import check_org_reputation

        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.BOUNCED,
            code=450,
        )

        check_org_reputation(org)

        org.refresh_from_db()
        assert not org.reputation_locked


class TestFblReportBuildArfBody:
    def test_build_arf_body__contains_feedback_type_abuse(self):
        body = FblReport.build_arf_body(
            source_ip="10.0.0.1",
            arrival_date="2026-01-01T00:00:00Z",
            envelope_from="spam@acme.com",
            rcpt_to="victim@example.com",
            delivery_result="spam",
            original_headers="From: spam@acme.com",
        )
        assert "Feedback-Type: abuse" in body
        assert "Original-Mail-From: spam@acme.com" in body
        assert "Delivery-Result: spam" in body


@pytest.mark.django_db
class TestComputeOrgReputationComplaintSources:
    def test_compute_org_reputation__counts_provider_fbl_as_complaint(self, org, user):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage
        from services.email.reputation.evaluation import compute_org_reputation

        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        FblReport.objects.create(
            org=org,
            mail_from="feedback@gmail.com",
            rcpt_to="fbl@acme.com",
            original_mail_from="sender@acme.com",
            source=FblReport.Source.PROVIDER,
        )

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 1

    def test_compute_org_reputation__ignores_relay_generated_fbl(self, org, user):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage
        from services.email.reputation.evaluation import compute_org_reputation

        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        FblReport.objects.create(
            org=org,
            mail_from="fbl@relay.local",
            rcpt_to="fbl@acme.com",
            original_mail_from="sender@acme.com",
            source=FblReport.Source.RELAY,
        )

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 0

    def test_compute_org_reputation__held_message_not_double_counted_by_fbl(
        self, org, user
    ):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage
        from services.email.reputation.evaluation import compute_org_reputation

        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.HELD,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        FblReport.create_for_spam(message)

        stats = compute_org_reputation(org)

        assert stats["complaints"] == 1


@pytest.mark.django_db
class TestReputationSignals:
    def make_sent_message(self, user, org):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage

        message = OutgoingMessage(
            sender=user,
            org=org,
            mail_from="sender@acme.com",
            rcpt_to="rcpt@example.com",
            status=OutgoingMessage.Status.SENT,
        )
        message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
        message.save(force_insert=True)
        return message

    def test_hard_bounce_triggers_lock(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        from services.email.msa.models import Transmission

        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = self.make_sent_message(user, org)

        with django_capture_on_commit_callbacks(execute=True):
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.BOUNCED,
                code=550,
            )

        org.refresh_from_db()
        assert org.reputation_locked

    def test_soft_bounce_does_not_trigger_check(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        from services.email.msa.models import Transmission

        settings.RELAY_REPUTATION_MIN_VOLUME = 1
        message = self.make_sent_message(user, org)

        with django_capture_on_commit_callbacks(execute=True):
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.BOUNCED,
                code=450,
            )

        org.refresh_from_db()
        assert not org.reputation_locked

    def test_held_message_triggers_lock(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage

        settings.RELAY_REPUTATION_MIN_VOLUME = 1

        with django_capture_on_commit_callbacks(execute=True):
            message = OutgoingMessage(
                sender=user,
                org=org,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                status=OutgoingMessage.Status.HELD,
            )
            message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
            message.save(force_insert=True)

        org.refresh_from_db()
        assert org.reputation_locked

    def test_regular_send_does_not_trigger_check(
        self, django_capture_on_commit_callbacks, org, user, settings
    ):
        from django.core.files.base import ContentFile

        from services.email.msa.models import OutgoingMessage

        settings.RELAY_REPUTATION_MIN_VOLUME = 1

        with django_capture_on_commit_callbacks(execute=True):
            message = OutgoingMessage(
                sender=user,
                org=org,
                mail_from="sender@acme.com",
                rcpt_to="rcpt@example.com",
                status=OutgoingMessage.Status.SENT,
            )
            message.raw_body.save("test.eml", ContentFile(b"x"), save=False)
            message.save(force_insert=True)

        org.refresh_from_db()
        assert not org.reputation_locked
