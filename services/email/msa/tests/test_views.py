from email import message_from_bytes
from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils.http import http_date

from domains.dkim import sign_message
from domains.models import Domain
from services.email.msa.models import (
    MsaCredential,
    OutgoingMessage,
    SuppressionEntry,
    Transmission,
)


def make_message(org, user, **kwargs):
    domain = kwargs.pop("domain", None) or Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    msg = OutgoingMessage(
        org=org,
        domain=domain,
        rcpt_to=kwargs.get("rcpt_to", "bob@example.com"),
        mail_from=kwargs.get("mail_from", "alice@example.com"),
        subject=kwargs.get("subject", "Test"),
        status=kwargs.get("status", OutgoingMessage.Status.PENDING),
    )
    raw = EmailMessage()
    raw["From"] = msg.mail_from
    raw["To"] = msg.rcpt_to
    raw["Subject"] = msg.subject
    raw.set_content("Hello world")
    msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw.as_bytes()), save=False)
    msg.save()
    return msg


@pytest.mark.django_db
class TestMessageDetailView:
    def test_get__ok_for_member(self, admin_client, org, user):
        msg = make_message(org, user)
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        assert response.context["message"] == msg

    def test_get__sets_etag_and_last_modified(self, admin_client, org, user):
        msg = make_message(org, user)
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        assert response.headers["ETag"] == (
            f'"{int(msg.pk):x}-{int(msg.modified_at.timestamp() * 1e6):x}"'
        )
        assert response.headers["Last-Modified"] == http_date(
            msg.modified_at.timestamp()
        )
        assert response.headers["Cache-Control"] == "private, no-cache"

    def test_get__not_modified_when_etag_matches(self, admin_client, org, user):
        msg = make_message(org, user)
        url = f"/org/{org.slug}/email/messages/{msg.id}"
        etag = admin_client.get(url).headers["ETag"]
        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 304

    def test_get__renders_when_message_changed(self, admin_client, org, user):
        msg = make_message(org, user)
        url = f"/org/{org.slug}/email/messages/{msg.id}"
        etag = admin_client.get(url).headers["ETag"]
        msg.status = OutgoingMessage.Status.SENT
        msg.save(update_fields=["status", "modified_at"])
        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 200
        assert response.headers["ETag"] != etag

    def test_get__not_found_for_other_org_message(
        self, admin_client, org, user, write_org
    ):
        other_user = User.objects.create_user(username="z", email="z@example.com")
        msg = make_message(write_org, other_user)
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 404

    def test_get__context_has_headers_and_parts(self, admin_client, org, user):
        msg = make_message(org, user)
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        assert "headers" in response.context
        assert "transmissions" in response.context

    def test_get__shows_stored_headers_and_dkim_signatures(
        self, admin_client, org, user
    ):
        msg = make_message(org, user)
        msg.headers = [
            ["From", "alice@example.com"],
            ["Subject", "Test"],
            [
                "DKIM-Signature",
                (
                    "v=1; a=ed25519-sha256; d=acme.com; s=relay; h=from:subject; "
                    "bh=AAAA; b=BBBB"
                ),
            ],
        ]
        msg.save(update_fields=["headers"])
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        # DKIM-Signature rows have their own card and are excluded from the
        # generic headers table.
        assert response.context["headers"] == [
            ["From", "alice@example.com"],
            ["Subject", "Test"],
        ]
        assert response.context["dkim_signatures"] == []

    def test_get__verifies_dkim_signatures_from_raw_body(self, admin_client, org, user):
        msg = make_message(org, user)
        raw = sign_message(msg.raw_bytes(), msg.domain)
        msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw), save=False)
        msg.save(update_fields=["raw_body"])
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        signatures = response.context["dkim_signatures"]
        assert [signature["result"] for signature in signatures] == [
            "pass",
            "pass",
        ]
        assert [signature["d"] for signature in signatures] == [
            msg.domain.name,
            msg.domain.name,
        ]
        msg.refresh_from_db()
        assert msg.dkim_results == signatures

    def test_get__malformed_dkim_signature_does_not_crash(
        self, admin_client, org, user
    ):
        msg = make_message(org, user)
        raw = msg.raw_bytes().replace(
            b"\n\n",
            b"\nDKIM-Signature: v=1; a=ed25519-sha256; b\n\n",
            1,
        )
        msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw), save=False)
        msg.save(update_fields=["raw_body"])
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        assert response.context["dkim_signatures"] == [
            {"v": "1", "a": "ed25519-sha256", "result": "permerror"}
        ]


@pytest.mark.django_db
class TestTestEmailView:
    def test_post__creates_message_and_redirects(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        org,
        user,
    ):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        with (
            patch("services.email.msa.handlers.check_outgoing_spam") as spam_task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = admin_client.post(
                f"/org/{org.slug}/email/messages/test",
                {"domain": str(domain.pk), "subject": "Test", "body": "Hello"},
            )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org, subject="Test")
        assert msg.subject == "Test"
        assert msg.domain == domain
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(msg.id), client_ip="127.0.0.1"
        )

    def test_post__signs_message_and_mints_feedback_id(self, admin_client, org, user):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk), "subject": "Test", "body": "Hello"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        stored = message_from_bytes(msg.raw_body.read())
        assert any(name == "Feedback-ID" for name, _ in msg.headers)
        assert any(name == "DKIM-Signature" for name, _ in msg.headers)
        assert msg.feedback_id
        assert msg.feedback_id == stored["Feedback-ID"]

    def test_post__records_submission(self, admin_client, org, user):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk), "subject": "Test", "body": "Hello"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.SUBMITTED

    def test_post__with_real_domain(self, admin_client, org, user):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk), "subject": "Hi", "body": "World"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org, subject="Hi")
        assert msg.domain == domain

    def test_post__does_not_use_domain_from_other_org(
        self,
        admin_client,
        org,
        write_org,
        user,
    ):
        domain = Domain.objects.create(name="other.com", org=write_org)
        admin_client.raise_request_exception = False

        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk), "subject": "Cross-org", "body": "Hello"},
        )

        assert response.status_code == 404
        assert not OutgoingMessage.objects.filter(
            org=org,
            subject="Cross-org",
        ).exists()


@pytest.mark.django_db
class TestCredentialListView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/credentials/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    @pytest.mark.django_db
    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_get__filters_by_org(self, admin_client, org, write_org):
        MsaCredential.objects.create_with_key(org=org, name="mine")
        MsaCredential.objects.create_with_key(org=write_org, name="theirs")
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert response.status_code == 200
        creds = list(response.context["credentials"])
        assert len(creds) == 1
        assert creds[0].name == "mine"

    def test_get__context_has_smtp_info(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert "smtp_hostname" in response.context
        assert "smtp_starttls_ports" in response.context
        assert "smtp_implicit_tls_ports" in response.context

    @pytest.mark.django_db
    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/credentials/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestCredentialCreateView:
    def test_post__creates_credential(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/credentials/new", {"name": "Production"}
        )
        assert response.status_code == 302
        cred = MsaCredential.objects.get(org=org)
        assert cred.name == "Production"

    def test_post__stores_raw_key_in_session(self, admin_client, org):
        admin_client.post(f"/org/{org.slug}/email/credentials/new", {"name": "Prod"})
        assert "raw_key" in admin_client.session


@pytest.mark.django_db
class TestCredentialDeleteView:
    def test_post__removes_credential(self, admin_client, org):
        cred, _ = MsaCredential.objects.create_with_key(org=org, name="old")
        response = admin_client.post(
            f"/org/{org.slug}/email/credentials/{cred.pk}/delete"
        )
        assert response.status_code == 302
        assert not MsaCredential.objects.filter(pk=cred.pk).exists()

    def test_post__not_found_for_other_org(self, admin_client, org, write_org):
        cred, _ = MsaCredential.objects.create_with_key(org=write_org, name="x")
        response = admin_client.post(
            f"/org/{org.slug}/email/credentials/{cred.pk}/delete"
        )
        assert response.status_code == 404


class TestSuppressionListView:
    @pytest.mark.django_db
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/suppression/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    @pytest.mark.django_db
    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/suppression/")
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_get__filters_by_org(self, admin_client, org, write_org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="mine@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        SuppressionEntry.objects.create_or_update(
            org=write_org,
            email="theirs@example.com",
            reason=SuppressionEntry.Reason.MANUAL,
        )
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")
        assert response.status_code == 200
        entries = list(response.context["object_list"])
        assert len(entries) == 1
        assert entries[0].address_hash == SuppressionEntry.hash_address(
            "mine@example.com"
        )

    @pytest.mark.django_db
    def test_get__context_has_chart(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")
        assert "suppression_chart" in response.context


class TestSuppressionCreateView:
    @pytest.mark.django_db
    def test_post__creates_entry(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/add",
            {"email": "bob@example.com"},
        )
        assert response.status_code == 302
        entry = SuppressionEntry.objects.get(org=org)
        assert entry.reason == SuppressionEntry.Reason.MANUAL

    @pytest.mark.django_db
    def test_post__updates_existing_entry(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/add",
            {"email": "bob@example.com"},
        )
        assert response.status_code == 302
        assert SuppressionEntry.objects.filter(org=org).count() == 1

    @pytest.mark.django_db
    def test_post__invalid_email_returns_400(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/add",
            {"email": "not-an-email"},
        )
        assert response.status_code == 400


class TestSuppressionRemoveView:
    @pytest.mark.django_db
    def test_post__removes_entry(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/remove",
            {"email": "bob@example.com"},
        )
        assert response.status_code == 302
        assert not SuppressionEntry.objects.filter(
            org=org, address_hash__email="bob@example.com"
        ).exists()

    @pytest.mark.django_db
    def test_post__not_found_returns_404(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/remove",
            {"email": "nobody@example.com"},
        )
        assert response.status_code == 404


class TestSuppressionCheckView:
    @pytest.mark.django_db
    def test_post__suppressed_returns_warning(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/check",
            {"email": "bob@example.com"},
        )
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_post__not_suppressed_returns_success(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/check",
            {"email": "nobody@example.com"},
        )
        assert response.status_code == 302

    @pytest.mark.django_db
    @pytest.mark.django_db
    def test_post__invalid_email_returns_400(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/check",
            {"email": "not-an-email"},
        )
        assert response.status_code == 400
