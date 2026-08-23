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
        assert report.feedback_type == "abuse"
        assert report.user_agent == "relay"
        assert report.original_mail_from == "sender@acme.com"
        assert report.domain == domain
        assert report.org == org


@pytest.mark.django_db
class TestComputeDomainReputationSpamHeld:
    def test_compute_domain_reputation__counts_held_spam_as_complaints(self, org, user):

        from django.core.files.base import ContentFile

        from domains.models import Domain
        from services.email.msa.models import OutgoingMessage
        from services.email.reputation.evaluation import compute_domain_reputation

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

        stats = compute_domain_reputation(domain)
        assert stats["complaints"] == 3
        assert stats["total_sent"] == 3


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
