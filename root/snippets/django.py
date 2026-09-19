# settings.py
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.relay.example.com",
            "port": 465,
            "use_ssl": True,
            "username": "acme",
            "password": "<credential key>",
        },
    },
}

# send from anywhere
from django.core.mail import send_mail

send_mail("Invoice 42", "Attached.", "billing@acme.com", ["kim@example.net"])


# views.py: receive inbound email via standard webhooks
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from standardwebhooks import Webhook


@csrf_exempt
def email_received(request):
    Webhook("<whsec_...>").verify(request.body, request.headers)
    event = json.loads(request.body)  # type == email.received
    ...  # download event["body_url"]
    return HttpResponse(status=204)
