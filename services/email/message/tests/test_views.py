from uuid import uuid4

import pytest

from domains.models import Domain
from kms.models import Certificate
from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.models import IncomingMessage


def make_certificate(issuer_certificate=None):
    return Certificate.objects.create(
        fingerprint=uuid4().hex,
        subject=f"CN={uuid4().hex[:12]}",
        issuer_certificate=issuer_certificate,
    )


def make_incoming(org, tls_certificate=None):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    return IncomingMessage.objects.create(
        org=org,
        domain=domain,
        receiving_domain="app.acme.com",
        mail_from="alice@external.com",
        rcpt_to="bob@app.acme.com",
        tls_certificate=tls_certificate,
    )


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
class TestMessageDetailOrgScoping:
    def test_get__incoming_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_incoming(write_org)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 404

    def test_get__outgoing_not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_transmission(write_org).message
        response = admin_client.get(f"/org/{org.slug}/email/messages/{msg.id}")
        assert response.status_code == 404
