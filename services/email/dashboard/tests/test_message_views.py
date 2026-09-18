from urllib.parse import quote
from uuid import uuid4

import pytest
from django.utils import timezone

from domains.models import Domain
from kms.models import Certificate
from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage


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
class TestMessageDetailOrgScoping:
    def test_get__incoming_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_incoming(write_org)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 404

    def test_get__outgoing_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_transmission(write_org).message
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 404
