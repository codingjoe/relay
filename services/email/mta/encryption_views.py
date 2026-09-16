from http import HTTPStatus

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from abstract.views import JSONBodyView
from accounts.views import OrganizationScopedView
from services.email.message.models import Message

from .models import Webhook, WebhookEncryptionKey


class WebhookEncryptionKeyView(OrganizationScopedView, JSONBodyView, View):
    """Set or remove the webhook recipient's X25519 public key."""

    def post(self, request, webhook_pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=webhook_pk, org=self.org)
        if self.body_data is None:
            return JsonResponse(
                {"error": "Invalid JSON body."},
                status=HTTPStatus.BAD_REQUEST,
            )
        try:
            public_key, key_id = (
                self.body_data["public_key"],
                self.body_data["key_id"],
            )
        except KeyError as missing:
            return JsonResponse(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=HTTPStatus.BAD_REQUEST,
            )
        try:
            webhook_key = webhook.encryption_key
        except WebhookEncryptionKey.DoesNotExist:
            webhook_key = WebhookEncryptionKey(
                webhook=webhook,
                public_key=public_key,
                key_id=key_id,
            )
            webhook_key.save(force_insert=True)
        else:
            webhook_key.public_key = public_key
            webhook_key.key_id = key_id
            webhook_key.save(update_fields=["public_key", "key_id", "modified_at"])
        return JsonResponse(
            {"key_id": webhook_key.key_id},
            status=HTTPStatus.CREATED,
        )

    def delete(self, request, webhook_pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=webhook_pk, org=self.org)
        get_object_or_404(WebhookEncryptionKey, webhook=webhook).delete()
        return HttpResponse(status=HTTPStatus.NO_CONTENT)


class SealedFileKeyView(OrganizationScopedView, JSONBodyView, View):
    """Return the sealed file key for a message."""

    def get(self, request, pk, *args, **kwargs):
        message = get_object_or_404(Message, pk=pk, org=self.org)
        if not message.sealed_file_key:
            return JsonResponse(
                {"error": "This message has no sealed file key."},
                status=HTTPStatus.NOT_FOUND,
            )
        return JsonResponse(
            {
                "sealed_file_key": message.sealed_file_key,
                "org_encryption_key_id": message.org_encryption_key_id,
            }
        )
