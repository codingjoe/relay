import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from domains.models import Domain
from services.email.mta.models import (
    IncomingMessage,
    TlsFailure,
    TlsReport,
    Webhook,
    WebhookDelivery,
)


def make_incoming(org, raw_body=b"From: a@b\r\nTo: c@d\r\nSubject: hi\r\n\r\nbody"):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
        subject="hi",
        message_id="<abc@example.com>",
    )
    msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw_body), save=False)
    msg.save()
    return msg


def make_webhook(org, url, pattern="*@example.com"):
    domain = Domain.objects.create(name=f"hook-{org.slug}.com", org=org)
    return Webhook.objects.create(
        org=org,
        url=url,
        name="",
        address_pattern=f"*@{domain.name}",
        domain=domain,
    )


class _CaptureHandler(BaseHTTPRequestHandler):
    status_code = 200
    requests: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        type(self).requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body,
            }
        )
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args, **kwargs):  # silence stderr
        pass


@pytest.fixture
def webhook_server():
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    _CaptureHandler.requests = []
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.django_db
class TestIncomingMessageDetailView:
    def test_get__ok_for_member(self, admin_client, org):
        msg = make_incoming(org)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 200
        assert response.context["message"] == msg

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_incoming(write_org)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 404

    def test_get__not_modified_when_etag_matches(self, admin_client, org):
        msg = make_incoming(org)
        url = f"/org/{org.slug}/email/incoming/{msg.id}"
        etag = admin_client.get(url).headers["ETag"]
        response = admin_client.get(url, headers={"If-None-Match": etag})
        assert response.status_code == 304

    def test_get__no_store_on_list(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/reports/?type=tls")
        assert response.headers["Cache-Control"] == "no-store"

    def test_get__context_has_headers(self, admin_client, org):
        raw = (
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Subject: hi\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hello body"
        )
        msg = make_incoming(org, raw_body=raw)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 200
        assert "headers" in response.context
        assert "webhook_deliveries" in response.context
        assert any(h[0] == "Subject" for h in response.context["headers"])

    def test_get__renders_webhook_deliveries(self, admin_client, org):
        msg = make_incoming(org)
        webhook = make_webhook(org, url="https://example.com/hook")
        now = timezone.now()
        WebhookDelivery.objects.create(
            message=msg,
            webhook=webhook,
            status=WebhookDelivery.Status.SENT,
            started_at=now,
            finished_at=now,
            response_code=200,
        )

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")

        assert response.status_code == 200
        assert [
            delivery.webhook for delivery in response.context["webhook_deliveries"]
        ] == [webhook]

    def test_get__handles_multipart(self, admin_client, org):
        raw = (
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Subject: hi\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=BOUND\r\n"
            b"\r\n"
            b"--BOUND\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"plain text\r\n"
            b"--BOUND--\r\n"
        )
        msg = make_incoming(org, raw_body=raw)
        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")
        assert response.status_code == 200

    def test_get__download_names_the_eml_like_the_stored_file(self, admin_client, org):
        msg = make_incoming(org)

        response = admin_client.get(f"/org/{org.slug}/email/incoming/{msg.id}")

        assert response.status_code == 200
        assert f'download="{msg.id}.eml"' in response.content.decode()


@pytest.mark.django_db
class TestWebhookListView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="empty"' in content
        assert "No endpoints yet." in content

    def test_get__no_store_cache_control_header(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.headers["Cache-Control"] == "no-store"

    def test_get__context_has_webhook_payload(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200
        assert "webhook_payload" in response.context
        assert '"type": "email.received"' in response.context["webhook_payload"]
        assert b"codehilite" in response.content

    def test_get__copy_button_escapes_signing_secret(
        self, admin_client, org, webhook_server
    ):
        webhook = make_webhook(org, url=f"{webhook_server}/x")
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200
        content = response.content.decode()
        assert f'data-copy="{webhook.signing_secret}"' in content
        assert 'aria-label="Copy signing secret"' in content

    def test_get__filters_by_org(self, admin_client, org, write_org, webhook_server):
        make_webhook(org, url=f"{webhook_server}/a")
        make_webhook(write_org, url=f"{webhook_server}/b")
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200
        webhooks = list(response.context["webhooks"])
        assert len(webhooks) == 1
        assert webhooks[0].org == org

    def test_get__domain_choices_are_scoped_to_org(
        self,
        admin_client,
        org,
        write_org,
    ):
        own_domain = Domain.objects.create(name="example.com", org=org)
        Domain.objects.create(name="other.com", org=write_org)

        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")

        assert own_domain in response.context["domain_choices"]
        assert not response.context["domain_choices"].filter(org=write_org).exists()

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/webhooks/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestWebhookCreateView:
    def test_post__creates_webhook(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "My hook",
                "domain": str(domain.pk),
            },
        )
        assert response.status_code == 302
        webhook = Webhook.objects.get(org=org)
        assert webhook.url == "https://example.com/hook"
        assert webhook.name == "My hook"
        assert webhook.address_pattern == "*@example.com"
        assert webhook.signing_secret.startswith("whsec_")

    def test_post__uses_address_pattern_prefix(self, admin_client, org):
        domain = Domain.objects.create(name="example.com", org=org)
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "",
                "pattern_prefix": "support",
                "domain": str(domain.pk),
            },
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/webhooks/")
        assert Webhook.objects.get(org=org).address_pattern == "support@example.com"

    def test_post__rejects_domain_from_other_org(
        self,
        admin_client,
        org,
        write_org,
    ):
        domain = Domain.objects.create(name="other.com", org=write_org)

        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "",
                "domain": str(domain.pk),
            },
        )

        assert response.status_code == 302
        assert not Webhook.objects.filter(org=org).exists()

    def test_post__not_found_for_non_member(self, admin_client, write_org):
        domain = Domain.objects.create(name="example.com", org=write_org)
        response = admin_client.post(
            f"/org/{write_org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "",
                "domain": str(domain.pk),
            },
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestWebhookDeleteView:
    def test_post__removes_webhook(self, admin_client, org, webhook_server):
        webhook = make_webhook(org, url=f"{webhook_server}/x")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/delete"
        )
        assert response.status_code == 302
        assert not Webhook.objects.filter(pk=webhook.pk).exists()

    def test_post__redirects_to_list(self, admin_client, org, webhook_server):
        webhook = make_webhook(org, url=f"{webhook_server}/x")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/delete"
        )
        assert response.url.endswith(f"/org/{org.slug}/email/webhooks/")

    def test_post__not_found_for_other_org(
        self, admin_client, org, write_org, webhook_server
    ):
        webhook = make_webhook(write_org, url=f"{webhook_server}/x")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/delete"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestWebhookTestView:
    def test_post__delivers_to_local_server(self, admin_client, org, webhook_server):
        webhook = make_webhook(org, url=f"{webhook_server}/hook")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/test"
        )
        assert response.status_code == 302
        assert _CaptureHandler.requests
        req = _CaptureHandler.requests[0]
        assert req["path"] == "/hook"
        assert req["headers"]["webhook-id"].startswith("msg_")
        assert "webhook-timestamp" in req["headers"]
        assert req["headers"]["webhook-signature"].startswith("v1,")
        delivery = WebhookDelivery.objects.get(webhook=webhook)
        assert delivery.is_test is True
        assert delivery.status == WebhookDelivery.Status.SENT

    def test_post__records_failure(self, admin_client, org, webhook_server):
        _CaptureHandler.status_code = 500
        webhook = make_webhook(org, url=f"{webhook_server}/hook")
        try:
            response = admin_client.post(
                f"/org/{org.slug}/email/webhooks/{webhook.pk}/test"
            )
        finally:
            _CaptureHandler.status_code = 200
        assert response.status_code == 302
        delivery = WebhookDelivery.objects.get(webhook=webhook)
        assert delivery.status == WebhookDelivery.Status.FAILED

    def test_post__not_found_for_other_org(
        self, admin_client, org, write_org, webhook_server
    ):
        webhook = make_webhook(write_org, url=f"{webhook_server}/x")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/test"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestTlsReportDetailView:
    def test_get__marks_the_relay_sending_ip(self, client, org, settings):
        settings.SMTP_SOURCE_IPS = ["10.0.0.9"]
        domain = Domain.objects.create(name="tls.example", org=org)
        report = TlsReport.objects.create(
            org=org,
            domain=domain,
            receiving_domain="tls.example",
            mail_from="reporter@example.com",
            rcpt_to="tls@tls.example",
            report_id="tls-1",
        )
        TlsFailure.objects.create(
            report=report,
            policy_type=TlsFailure.PolicyType.STS,
            result_type=TlsFailure.ResultType.CERTIFICATE_EXPIRED,
            sending_mta_ip_address="10.0.0.9",
        )
        client.force_login(org.members.first())  # noqa: any member

        response = client.get(
            reverse(
                "mta:tls-report-detail",
                kwargs={"org_slug": org.slug, "pk": report.pk},
            )
        )

        assert response.status_code == 200
        assert "Sent by relay" in response.content.decode()
