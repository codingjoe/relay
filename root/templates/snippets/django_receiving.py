# views.py
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from standardwebhooks import Webhook


@csrf_exempt
def email_received(request):
    Webhook("<whsec_...>").verify(request.body, request.headers)
    event = json.loads(request.body)  # type == email.received
    # download event["body_url"]
    return HttpResponse(status=204)
