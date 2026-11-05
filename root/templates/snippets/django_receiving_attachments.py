# views.py
import email
import json
import os
import urllib.request

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from standardwebhooks import Webhook

WEBHOOK_SIGNING_SECRET = os.environ["WEBHOOK_SIGNING_SECRET"]


@csrf_exempt
def email_received(request):
    Webhook(WEBHOOK_SIGNING_SECRET).verify(request.body, request.headers)
    event = json.loads(request.body)  # type == email.received
    with urllib.request.urlopen(event["body_url"], timeout=30) as response:
        message = email.message_from_bytes(response.read())
    for part in message.walk():
        match part.get_content_type():
            case "application/pdf":
                invoice = SimpleUploadedFile(
                    part.get_filename() or "invoice.pdf",
                    part.get_payload(decode=True),
                    "application/pdf",
                )
                # ...
    return HttpResponse(status=204)
