import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.core.files.base import ContentFile

from domains.models import Domain
from kms.models import SigningKey
from mx.models import IncomingMessage, Webhook, WebhookDelivery


def make_incoming(org, raw_body=b"From: a@b\r\nTo: c@d\r\nSubject: hi\r\n\r\nbody"):
    msg = IncomingMessage(
        org=org,
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
    signing_key = SigningKey.generate("ed25519")
    return Webhook.objects.create(
        org=org,
        url=url,
        name="",
        address_pattern=pattern,
        signing_key=signing_key,
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
class TestIncomingMessageListView:
    """Legacy /email/inbox/ redirects to the merged contact timeline."""

    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/inbox/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__redirects_to_contact_timeline(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/inbox/")
        assert response.status_code == 302
        assert (
            response.url
            == f"/org/{org.slug}/email/contacts/messages/?direction=received"
        )

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/inbox/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestIncomingMessageDetailView:
    def test_get__ok_for_member(self, admin_client, org):
        msg = make_incoming(org)
        response = admin_client.get(f"/org/{org.slug}/email/inbox/{msg.id}")
        assert response.status_code == 200
        assert response.context["message"] == msg

    def test_get__not_found_for_other_org(self, admin_client, org, write_org):
        msg = make_incoming(write_org)
        response = admin_client.get(f"/org/{org.slug}/email/inbox/{msg.id}")
        assert response.status_code == 404

    def test_get__context_has_headers_and_parts(self, admin_client, org):
        raw = (
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Subject: hi\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hello body"
        )
        msg = make_incoming(org, raw_body=raw)
        response = admin_client.get(f"/org/{org.slug}/email/inbox/{msg.id}")
        assert response.status_code == 200
        assert "headers" in response.context
        assert "parts" in response.context
        assert "webhook_deliveries" in response.context
        assert any(h[0] == "Subject" for h in response.context["headers"])

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
        response = admin_client.get(f"/org/{org.slug}/email/inbox/{msg.id}")
        assert response.status_code == 200
        assert len(response.context["parts"]) >= 1


@pytest.mark.django_db
class TestWebhookListView:
    def test_get__requires_login(self, client, org):
        response = client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 302
        assert "/account/login" in response.url

    def test_get__ok_for_member(self, admin_client, org):
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200

    def test_get__filters_by_org(self, admin_client, org, write_org, webhook_server):
        make_webhook(org, url=f"{webhook_server}/a")
        make_webhook(write_org, url=f"{webhook_server}/b")
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert response.status_code == 200
        webhooks = list(response.context["webhooks"])
        assert len(webhooks) == 1
        assert webhooks[0].org == org

    def test_get__context_has_domain_choices(self, admin_client, org):
        Domain.objects.create(name="example.com", org=org)
        response = admin_client.get(f"/org/{org.slug}/email/webhooks/")
        assert "domain_choices" in response.context
        names = [d[0] for d in response.context["domain_choices"]]
        assert "example.com" in names

    def test_get__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.get(f"/org/{write_org.slug}/email/webhooks/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestWebhookCreateView:
    def test_post__creates_webhook(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "My hook",
                "pattern_prefix": "*",
                "domain_part": "example.com",
            },
        )
        assert response.status_code == 302
        webhook = Webhook.objects.filter(org=org).first()
        assert webhook is not None
        assert webhook.url == "https://example.com/hook"
        assert webhook.name == "My hook"
        assert webhook.address_pattern == "*@example.com"
        assert webhook.signing_key is not None

    def test_post__redirects_to_list(self, admin_client, org):
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "",
                "pattern_prefix": "support",
                "domain_part": "example.com",
            },
        )
        assert response.status_code == 302
        assert response.url.endswith(f"/org/{org.slug}/email/webhooks/")

    def test_post__not_found_for_non_member(self, admin_client, write_org):
        response = admin_client.post(
            f"/org/{write_org.slug}/email/webhooks/new",
            {
                "url": "https://example.com/hook",
                "name": "",
                "pattern_prefix": "*",
                "domain_part": "example.com",
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
        assert req["headers"]["webhook-signature"].startswith("v1a,")
        delivery = WebhookDelivery.objects.filter(webhook=webhook).first()
        assert delivery is not None
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
        delivery = WebhookDelivery.objects.filter(webhook=webhook).first()
        assert delivery.status == WebhookDelivery.Status.FAILED

    def test_post__not_found_for_other_org(
        self, admin_client, org, write_org, webhook_server
    ):
        webhook = make_webhook(write_org, url=f"{webhook_server}/x")
        response = admin_client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/test"
        )
        assert response.status_code == 404
