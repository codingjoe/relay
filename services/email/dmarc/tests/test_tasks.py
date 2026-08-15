import pytest
from django.core import mail
from django.core.files.base import ContentFile

from domains.models import Domain
from services.email.dmarc.tasks import (
    evaluate_incoming_message,
    generate_daily_rua_reports,
)
from services.email.mx.models import IncomingMessage

DMARC_REJECT = (
    '"v=DMARC1; p=reject; rua=mailto:rua@example.org; ruf=mailto:ruf@example.org"'
)


def make_incoming(org, *, sealed_file_key="", raw_body=b""):
    domain = Domain.objects.get(org=org, is_managed=True)
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain=domain.name,
        mail_from="sender@bad.example",
        rcpt_to=f"someone@{domain.name}",
        subject="hi",
        message_id="<abc@example.org>",
    )
    msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw_body), save=False)
    msg.sealed_file_key = sealed_file_key
    msg.save(force_insert=True)
    return msg


def raw_email():
    return (
        b"From: someone@example.org\r\nTo: bob@example.com\r\nSubject: hi\r\n\r\nbody"
    )


@pytest.mark.django_db
class TestEvaluateIncomingMessage:
    def test_evaluate_incoming_message__skips_encrypted(self, org):
        msg = make_incoming(
            org, sealed_file_key="sealed-file-key", raw_body=raw_email()
        )
        evaluate_incoming_message.enqueue(message_pk=str(msg.pk))
        assert len(mail.outbox) == 0

    def test_evaluate_incoming_message__evaluates_unencrypted(self, org, dns_resolver):
        dns_resolver.add("_dmarc.example.org", "TXT", DMARC_REJECT)
        msg = make_incoming(org, raw_body=raw_email())
        evaluate_incoming_message.enqueue(message_pk=str(msg.pk))
        assert len(mail.outbox) == 1
        assert "DMARC failure report" in mail.outbox[0].subject


@pytest.mark.django_db
class TestGenerateDailyRuaReports:
    def test_generate_daily_rua_reports__excludes_encrypted_messages(self, org):
        make_incoming(org, sealed_file_key="sealed-file-key", raw_body=raw_email())
        generate_daily_rua_reports.enqueue()
        assert len(mail.outbox) == 0
