from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import OrganizationScopedView

from .models import IncomingMessage, Webhook, WebhookEncryptionKey


class WebhookEncryptionKeyView(OrganizationScopedView, APIView):
    """Set or remove the webhook recipient's X25519 public key."""

    def post(self, request, webhook_pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=webhook_pk, org=self.org)
        try:
            public_key, key_id = (
                request.data["public_key"],
                request.data["key_id"],
            )
        except KeyError as missing:
            return Response(
                {"error": f"Missing required field: {missing.args[0]}"},
                status=status.HTTP_400_BAD_REQUEST,
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
        return Response(
            {"key_id": webhook_key.key_id},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, webhook_pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=webhook_pk, org=self.org)
        get_object_or_404(WebhookEncryptionKey, webhook=webhook).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SealedFileKeyView(OrganizationScopedView, APIView):
    """Return the sealed file key for an incoming message."""

    def get(self, request, pk, *args, **kwargs):
        message = get_object_or_404(IncomingMessage, pk=pk, org=self.org)
        if not message.sealed_file_key:
            return Response(
                {"error": "This message has no sealed file key."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "sealed_file_key": message.sealed_file_key,
                "org_encryption_key_id": message.org_encryption_key_id,
            }
        )
