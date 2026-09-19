import re
from urllib.parse import quote
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from domains.models import Domain
from kms.models import Certificate
from services.email.message.models import Transmission
from services.email.message.templatetags.message import human_duration
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage

MULTIPART_BODY = (
    b'MIME-Version: 1.0\r\nContent-Type: multipart/alternative; boundary="b"\r\n\r\n'
    b"--b\r\nContent-Type: text/plain\r\n\r\nplain body\r\n"
    b"--b\r\nContent-Type: text/html\r\n\r\n<p>html body</p>\r\n--b--\r\n"
)


def tab_order(content):
    return re.findall(r'id="(message-tab-[a-z]+)"', content)


def panel_visibility(content):
    return {
        panel_id: "hidden" in attributes
        for panel_id, attributes in re.findall(
            r'id="(message-panel-[a-z]+)"([^>]*)>', content
        )
    }


def make_certificate(issuer_certificate=None):
    return Certificate.objects.create(
        fingerprint=uuid4().hex,
        subject=f"CN={uuid4().hex[:12]}",
        issuer_certificate=issuer_certificate,
    )


def make_incoming(org, tls_certificate=None):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    message = IncomingMessage.objects.create(
        org=org,
        domain=domain,
        receiving_domain="app.acme.com",
        mail_from="alice@external.com",
        rcpt_to="bob@app.acme.com",
    )
    Transmission.objects.create(
        message=message,
        status=Transmission.Status.RECEIVED,
        tls_mode=Transmission.TlsMode.STARTTLS,
        tls_certificate=tls_certificate,
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )
    return message


def make_transmission(org, tls_certificate=None):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    msg = OutgoingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
    )
    return Transmission.objects.create(
        message=msg,
        status=Transmission.Status.SENT,
        tls_mode=Transmission.TlsMode.STARTTLS,
        tls_certificate=tls_certificate,
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )


@pytest.mark.django_db
class TestCertificateDetailView:
    def test_get__ok_for_message_certificate(self, admin_client, org):
        certificate = make_certificate()
        make_incoming(org, tls_certificate=certificate)
        response = admin_client.get(
            f"/org/{org.slug}/email/certificates/{certificate.fingerprint}"
        )
        assert response.status_code == 200
        assert response.context["certificate"] == certificate

    def test_get__ok_for_transmission_certificate(self, admin_client, org):
        certificate = make_certificate()
        make_transmission(org, tls_certificate=certificate)
        response = admin_client.get(
            f"/org/{org.slug}/email/certificates/{certificate.fingerprint}"
        )
        assert response.status_code == 200
        assert response.context["certificate"] == certificate

    def test_get__ok_for_chain_ancestor(self, admin_client, org):
        root = make_certificate()
        leaf = make_certificate(issuer_certificate=root)
        make_incoming(org, tls_certificate=leaf)
        response = admin_client.get(
            f"/org/{org.slug}/email/certificates/{root.fingerprint}"
        )
        assert response.status_code == 200
        assert response.context["certificate"] == root

    def test_get__not_found_for_other_org_message_certificate(
        self, admin_client, org, write_org
    ):
        certificate = make_certificate()
        make_incoming(write_org, tls_certificate=certificate)
        response = admin_client.get(
            f"/org/{org.slug}/email/certificates/{certificate.fingerprint}"
        )
        assert response.status_code == 404

    def test_get__not_found_for_other_org_transmission_certificate(
        self, admin_client, org, write_org
    ):
        certificate = make_certificate()
        make_transmission(write_org, tls_certificate=certificate)
        response = admin_client.get(
            f"/org/{org.slug}/email/certificates/{certificate.fingerprint}"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestMessageListDirectionChart:
    def test_get__keeps_outgoing_counts_above_the_axis(self, admin_client, org):
        domain = Domain.objects.get(org=org, is_managed=True)
        OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            mail_from="alice@example.com",
            rcpt_to="bob@example.com",
            status=OutgoingMessage.Status.SENT,
        )

        response = admin_client.get(f"/org/{org.slug}/email/messages/")

        assert response.status_code == 200
        assert response.context["chart"]["rows"][-1]["outgoing_sent"] == 1

    def test_get__mirrors_incoming_counts_below_the_axis(self, admin_client, org):
        make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/messages/")

        assert response.status_code == 200
        assert response.context["chart"]["rows"][-1]["incoming_received"] == -1

    def test_get__chart_counts_only_the_filtered_messages(self, admin_client, org):
        make_incoming(org)

        response = admin_client.get(
            f"/org/{org.slug}/email/messages/?email=nobody@example.com"
        )

        assert response.status_code == 200
        assert response.context["chart"]["rows"][-1]["incoming_received"] == 0


@pytest.mark.django_db
class TestMessageListCount:
    def test_get__shows_the_count_inside_the_search_input(self, admin_client, org):
        make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/messages/")

        assert response.status_code == 200
        group = re.search(
            r'<div class="input-group">.*?</div>', response.content.decode(), re.DOTALL
        )
        assert group is not None
        assert "1 message" in group.group()


@pytest.mark.django_db
class TestMessageDetailAddressLinks:
    def test_get__links_the_sender_to_the_filtered_list(self, admin_client, org):
        message = make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        content = response.content.decode()
        assert (
            f'href="/org/{org.slug}/email/messages/?email={quote(message.mail_from)}"'
            in content
        )
        assert (
            f'href="/org/{org.slug}/email/messages/?email={quote(message.rcpt_to)}"'
            in content
        )


@pytest.mark.django_db
class TestMessageDetailStatusCard:
    def test_get__shows_the_status_and_the_delivery_summary(self, admin_client, org):
        message = make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        assert response.context["delivery_attempts"] == 1
        assert response.context["delivery_finished_at"] is not None
        content = response.content.decode()
        assert 'data-variant="success"' in content
        assert human_duration(response.context["delivery_duration"]) in content

    def test_get__shows_the_scan_verdicts(self, admin_client, org):
        message = make_incoming(org)
        message.spam_action = "reject"
        message.spam_score = 10.0
        message.virus_action = "infected"
        message.virus_name = "Eicar-Test-Signature"
        message.save(
            update_fields=[
                "spam_action",
                "spam_score",
                "virus_action",
                "virus_name",
            ]
        )

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Spam reject" in content
        assert "Eicar-Test-Signature" in content

    def test_get__renders_tabs_with_the_html_body(self, admin_client, org):
        message = make_incoming(org)
        message.raw_body = SimpleUploadedFile("multipart.eml", MULTIPART_BODY)
        message.save(update_fields=["raw_body"])

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        content = response.content.decode()
        assert "<iframe" in content
        assert "sandbox" in content
        assert "allow-scripts" not in content
        assert response.context["html_body"] == "<p>html body</p>"

    def test_get__leads_with_the_html_body_and_ends_with_the_headers(
        self, admin_client, org
    ):
        message = make_incoming(org)
        message.raw_body = SimpleUploadedFile("multipart.eml", MULTIPART_BODY)
        message.save(update_fields=["raw_body"])

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        content = response.content.decode()
        assert tab_order(content) == [
            "message-tab-html",
            "message-tab-text",
            "message-tab-headers",
        ]
        assert panel_visibility(content) == {
            "message-panel-html": False,
            "message-panel-text": True,
            "message-panel-headers": True,
        }

    def test_get__omits_the_html_tab_without_an_html_part(self, admin_client, org):
        message = make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="message-tab-html"' not in content
        assert response.context["html_body"] == ""
        assert tab_order(content) == ["message-tab-text", "message-tab-headers"]
        assert panel_visibility(content) == {
            "message-panel-text": False,
            "message-panel-headers": True,
        }

    def test_get__omits_the_delivery_summary_without_attempts(self, admin_client, org):
        message = IncomingMessage.objects.create(
            org=org,
            domain=Domain.objects.get(org=org, is_managed=True),
            mail_from="alice@example.com",
            rcpt_to="bob@example.com",
        )

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{message.id}")

        assert response.status_code == 200
        assert "delivery_attempts" not in response.context
        assert "delivery_finished_at" not in response.context
        assert "delivery_duration" not in response.context


@pytest.mark.django_db
class TestMessageDetailOrgScoping:
    def test_get__incoming_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_incoming(write_org)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 404

    def test_get__outgoing_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_transmission(write_org).message
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 404
