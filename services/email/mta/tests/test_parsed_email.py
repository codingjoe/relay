import pytest
from django.core.files.base import ContentFile

from domains.models import Domain
from services.email.mta.models import IncomingMessage


def create_message(org, sealed_file_key=""):
    domain = Domain.objects.get(org=org, is_managed=True)
    raw = b"From: a@b\r\nTo: c@d\r\nSubject: hi\r\n\r\nbody"
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
        sealed_file_key=sealed_file_key,
    )
    msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw), save=False)
    msg.save(force_insert=True)
    return msg


@pytest.mark.django_db
class TestParsedEmail:
    def test_parsed_email__returns_none_for_encrypted_message(self, org):
        msg = create_message(org, sealed_file_key="sealed-file-key")
        assert msg.parsed_email() is None

    def test_parsed_email__parses_unencrypted_message(self, org):
        msg = create_message(org)
        parsed = msg.parsed_email()
        assert parsed is not None
        assert parsed["Subject"] == "hi"
