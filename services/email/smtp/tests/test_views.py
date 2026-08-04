from email.message import EmailMessage

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from services.email.smtp.models import OutgoingMessage, SmtpCredential


def make_message(org, user, **kwargs):
    msg = OutgoingMessage(
        sender=user,
        org=org,
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
@pytest.mark.django_db
class TestMessageDetailView:
    def test_get__ok_for_member(self, admin_client, org, user):
        msg = make_message(org, user)
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 200
        assert response.context["message"] == msg

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


@pytest.mark.django_db
class TestTestEmailView:
    def test_post__creates_message_and_redirects(self, admin_client, org, user):
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": "free", "subject": "Test", "body": "Hello"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.filter(org=org).first()
        assert msg is not None
        assert msg.sender == user
        assert msg.subject == "Test"

    def test_post__with_real_domain(self, admin_client, org, user):
        from domains.models import Domain

        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk), "subject": "Hi", "body": "World"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.filter(org=org).first()
        assert msg is not None
        assert msg.domain == domain


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
        SmtpCredential.objects.create_with_key(org=org, name="mine")
        SmtpCredential.objects.create_with_key(org=write_org, name="theirs")
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert response.status_code == 200
        creds = list(response.context["credentials"])
        assert len(creds) == 1
        assert creds[0].name == "mine"

    def test_get__context_has_smtp_info(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert "smtp_hostname" in response.context
        assert "smtp_port" in response.context

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
        cred = SmtpCredential.objects.filter(org=org).first()
        assert cred is not None
        assert cred.name == "Production"

    def test_post__stores_raw_key_in_session(self, admin_client, org):
        admin_client.post(f"/org/{org.slug}/email/credentials/new", {"name": "Prod"})
        assert "raw_key" in admin_client.session


@pytest.mark.django_db
class TestCredentialDeleteView:
    def test_post__removes_credential(self, admin_client, org):
        cred, _ = SmtpCredential.objects.create_with_key(org=org, name="old")
        response = admin_client.post(
            f"/org/{org.slug}/email/credentials/{cred.pk}/delete"
        )
        assert response.status_code == 302
        assert not SmtpCredential.objects.filter(pk=cred.pk).exists()

    def test_post__not_found_for_other_org(self, admin_client, org, write_org):
        cred, _ = SmtpCredential.objects.create_with_key(org=write_org, name="x")
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
        from services.email.smtp.models import SuppressionEntry

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
        from services.email.smtp.models import SuppressionEntry

        response = admin_client.post(
            f"/org/{org.slug}/email/suppression/add",
            {"email": "bob@example.com"},
        )
        assert response.status_code == 302
        entry = SuppressionEntry.objects.filter(org=org).first()
        assert entry is not None
        assert entry.reason == SuppressionEntry.Reason.MANUAL

    @pytest.mark.django_db
    def test_post__updates_existing_entry(self, admin_client, org):
        from services.email.smtp.models import SuppressionEntry

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
        from services.email.smtp.models import SuppressionEntry

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
        from services.email.smtp.models import SuppressionEntry

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
