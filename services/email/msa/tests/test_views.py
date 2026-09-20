import re
from email import message_from_bytes, policy
from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils.html import escape
from django.utils.http import http_date

from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.models import (
    MsaCredential,
    OutgoingMessage,
    SuppressionEntry,
)


def copy_button(content, value):
    """Return the copy button tag that carries `value`, or None."""
    return re.search(
        rf'<button[^>]*data-copy="{re.escape(value)}"[^>]*>',
        content,
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

    def test_get__shows_stored_headers_including_dkim_signatures(
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
        assert response.context["headers"] == [
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
        assert response.context["headers"][-1] == [
            "DKIM-Signature",
            "v=1; a=ed25519-sha256; b",
        ]


@pytest.mark.django_db
class TestTestEmailView:
    def test_post__creates_message_and_redirects(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        org,
    ):
        domain = Domain.objects.get(org=org, is_managed=True)
        with (
            patch("services.email.msa.handlers.check_outgoing_spam") as spam_task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        assert response.url == reverse(
            "message:message-list", kwargs={"org_slug": org.slug}
        )
        msg = OutgoingMessage.objects.get(org=org)
        assert msg.domain == domain
        spam_task.enqueue.assert_called_once_with(
            message_pk=str(msg.id), client_ip="127.0.0.1"
        )

    def test_post__sets_templated_headers(self, admin_client, org, user):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        stored = message_from_bytes(
            OutgoingMessage.objects.get(org=org).raw_body.read(),
            policy=policy.default,
        )
        assert stored["Subject"] == f"Test email from {domain.name}"
        assert stored["From"] == f"postmaster@{domain.name}"
        assert stored["To"] == user.email
        assert stored["Reply-To"] is None

    def test_post__stores_html_and_plain_parts(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        stored = message_from_bytes(
            OutgoingMessage.objects.get(org=org).raw_body.read(),
            policy=policy.default,
        )
        parts = {
            part.get_content_type(): part.get_content() for part in stored.iter_parts()
        }
        assert set(parts) == {"text/html", "text/plain"}
        assert f"postmaster@{domain.name}" in parts["text/html"]
        assert f"postmaster@{domain.name}" in parts["text/plain"]
        link = f"http://testserver/org/{org.slug}/email/messages/"
        assert f'href="{link}"' in parts["text/html"]
        assert f"<{link}>" in parts["text/plain"]

    def test_post__ignores_submitted_content(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": "", "subject": "Injected", "body": "Injected"},
        )
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        assert msg.subject == f"Test email from {domain.name}"
        assert b"Injected" not in msg.raw_body.read()

    def test_post__signs_message_and_mints_feedback_id(self, admin_client, org):
        response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        stored = message_from_bytes(msg.raw_body.read())
        assert any(name == "Feedback-ID" for name, _ in msg.headers)
        assert any(name == "DKIM-Signature" for name, _ in msg.headers)
        assert msg.feedback_id
        assert msg.feedback_id == stored["Feedback-ID"]

    def test_post__records_submission(self, admin_client, org):
        response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        transmission = Transmission.objects.get(message=msg)
        assert transmission.status == Transmission.Status.SUBMITTED

    def test_post__uses_managed_domain(self, admin_client, org):
        Domain.objects.create(name="example.com", org=org)
        response = admin_client.post(f"/org/{org.slug}/email/messages/test")
        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        assert msg.domain == Domain.objects.get(org=org, is_managed=True)

    def test_post__uses_selected_domain(self, admin_client, org):
        domain = Domain.objects.create(
            name="example.com",
            org=org,
            nameserver_status=Domain.Status.OK,
            spf_status=Domain.Status.OK,
            dkim_status=Domain.Status.OK,
            dmarc_status=Domain.Status.OK,
        )

        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(domain.pk)},
        )

        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        assert msg.domain == domain
        assert msg.mail_from == f"postmaster@{domain.name}"

    def test_post__does_not_use_domain_from_other_org(
        self,
        admin_client,
        org,
        write_org,
    ):
        other_domain = Domain.objects.get(org=write_org, is_managed=True)

        response = admin_client.post(
            f"/org/{org.slug}/email/messages/test",
            {"domain": str(other_domain.pk)},
        )

        assert response.status_code == 302
        msg = OutgoingMessage.objects.get(org=org)
        assert msg.domain == Domain.objects.get(org=org, is_managed=True)
        assert msg.domain != other_domain

    def test_post__without_managed_domain(self, admin_client, org):
        Domain.objects.filter(org=org, is_managed=True).delete()

        response = admin_client.post(f"/org/{org.slug}/email/messages/test")

        assert response.status_code == 302
        assert response.url == reverse(
            "message:message-list", kwargs={"org_slug": org.slug}
        )
        assert not OutgoingMessage.objects.filter(org=org).exists()
        assert any(
            "Add a sending domain first." in str(message)
            for message in get_messages(response.wsgi_request)
        )

    def test_post__refuses_suppressed_recipient(self, admin_client, org, user):
        SuppressionEntry.objects.create_or_update(
            org=org, email=user.email, reason=SuppressionEntry.Reason.MANUAL
        )

        response = admin_client.post(f"/org/{org.slug}/email/messages/test")

        assert response.status_code == 302
        assert not OutgoingMessage.objects.filter(org=org).exists()
        assert any(
            "Recipient is on the suppression list." in str(message)
            for message in get_messages(response.wsgi_request)
        )

    def test_post__refuses_recipient_without_address(self, admin_client, org, user):
        user.email = ""
        user.save(update_fields=["email"])

        response = admin_client.post(f"/org/{org.slug}/email/messages/test")

        assert response.status_code == 302
        assert not OutgoingMessage.objects.filter(org=org).exists()
        assert any(
            "Your account cannot receive email." in str(message)
            for message in get_messages(response.wsgi_request)
        )

    def test_post__stores_body_for_long_message_id(
        self, admin_client, org, monkeypatch
    ):
        # Long enough to outgrow the raw body file field, as the FQDN of a
        # CI runner does.
        monkeypatch.setattr(
            "django.core.mail.message.DNS_NAME",
            "runnervmlun5p.hiyczbto55aehk554uscjghr2a.gx.internal.cloudapp.net",
        )

        response = admin_client.post(f"/org/{org.slug}/email/messages/test")

        assert response.status_code == 302
        assert OutgoingMessage.objects.get(org=org).raw_body


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
        content = response.content.decode()
        assert 'class="empty"' in content
        assert "No credentials yet." in content

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
        assert response.context["smtp_uri"] == (
            "smtps://test-org:<credential key>@smtp.testserver:465"
        )

    def test_get__renders_connection_uri(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")
        assert response.status_code == 200
        assert (
            "smtps://test-org:&lt;credential key&gt;@smtp.testserver:465"
            in response.content.decode()
        )

    def test_get__opens_the_key_dialog_after_creation(self, admin_client, org):
        admin_client.post(f"/org/{org.slug}/email/credentials/new", {"name": "Prod"})
        raw_key = admin_client.session["raw_key"]

        response = admin_client.get(f"/org/{org.slug}/email/credentials/")

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="dlg-credential-key"' in content
        assert raw_key in content
        assert f"smtps://{org.slug}:{raw_key}@smtp.testserver:465" in content

    def test_get__renders_copy_buttons_in_the_key_dialog(self, admin_client, org):
        admin_client.post(f"/org/{org.slug}/email/credentials/new", {"name": "Prod"})
        raw_key = admin_client.session["raw_key"]

        response = admin_client.get(f"/org/{org.slug}/email/credentials/")

        content = response.content.decode()
        key_button = copy_button(content, raw_key)
        uri_button = copy_button(content, escape(response.context["smtp_uri_with_key"]))
        assert key_button is not None
        assert 'data-size="icon-xs"' in key_button.group()
        assert "aria-label='Copy key'" in key_button.group()
        assert uri_button is not None
        assert 'data-size="icon-xs"' in uri_button.group()
        assert "aria-label='Copy connection URI'" in uri_button.group()

    def test_get__renders_copy_buttons_in_the_connection_table(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")

        content = response.content.decode()
        buttons = [
            ("Copy server", response.context["smtp_hostname"]),
            ("Copy port", ", ".join(map(str, response.context["smtp_starttls_ports"]))),
            (
                "Copy port",
                ", ".join(map(str, response.context["smtp_implicit_tls_ports"])),
            ),
            ("Copy username", org.slug),
            ("Copy connection URI", escape(response.context["smtp_uri"])),
        ]
        for label, value in buttons:
            button = copy_button(content, value)
            assert button is not None, value
            assert 'data-size="icon"' in button.group(), value
            label_pattern = rf"aria-label=(?P<q>[\"']){re.escape(label)}(?P=q)"
            assert re.search(label_pattern, button.group()), value

    def test_get__opens_the_sending_docs_in_a_new_tab(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/credentials/")

        content = response.content.decode()

        assert (
            '<a class="link" href="/docs/sending/" target="_blank" rel="noopener">'
            "sending docs</a>"
        ) in content

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
    def test_get__leads_with_the_chart(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="mine@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")

        assert response.status_code == 200
        content = response.content.decode()
        assert content.index('id="chart-suppression"') < content.index(
            'id="form-suppression"'
        )

    @pytest.mark.django_db
    def test_get__counts_the_addresses_atop_the_card(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="one@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        SuppressionEntry.objects.create_or_update(
            org=org, email="two@example.com", reason=SuppressionEntry.Reason.BOUNCE
        )

        response = admin_client.get(f"/org/{org.slug}/email/suppression/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "two addresses on the suppression list" in content
        assert 'data-dialog="dlg-clear-suppression"' in content
        assert content.index('class="empty"') < content.index('id="form-suppression"')
        assert content.index('id="form-suppression"') < content.index(
            'id="dlg-clear-suppression"'
        )

    @pytest.mark.django_db
    def test_get__counts_no_addresses(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "0 addresses on the suppression list" in content
        assert 'data-dialog="dlg-clear-suppression"' not in content

    @pytest.mark.django_db
    def test_post__clears_the_list(self, admin_client, org):
        SuppressionEntry.objects.create_or_update(
            org=org, email="mine@example.com", reason=SuppressionEntry.Reason.MANUAL
        )

        response = admin_client.post(f"/org/{org.slug}/email/suppression/clear")

        assert response.status_code == 302
        assert not SuppressionEntry.objects.filter(org=org).exists()

    @pytest.mark.django_db
    def test_get__renders_one_address_form_for_all_actions(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/suppression/")

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="form-suppression"' in content
        assert (
            f'formaction="{reverse("msa:suppression-check", kwargs={"org_slug": org.slug})}"'
            in content
        )
        assert (
            f'formaction="{reverse("msa:suppression-remove", kwargs={"org_slug": org.slug})}"'
            in content
        )
        assert 'id="suppression-address"' in content

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
