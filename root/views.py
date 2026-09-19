from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import BreadcrumbViewMixin, CacheControlMixin

# Wordmarks of companies that back relay, with owner-attested endorsement.
# Optional keys: "url" (endorser link) and "logo" (static image path).
PYTHON_SNIPPET = """# settings.py
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
"""


TYPESCRIPT_SNIPPET = """import nodemailer from "nodemailer";

const transport = nodemailer.createTransport({
  host: "smtp.relay.example.com",
  port: 465,
  secure: true,
  auth: { user: "acme", pass: "<credential key>" },
});

await transport.sendMail({
  from: "billing@acme.com",
  to: "kim@example.net",
  subject: "Invoice 42",
  text: "Attached.",
});


// app/api/email/route.ts: receive inbound email via standard webhooks
import { Webhook } from "standardwebhooks";

export async function POST(req: Request) {
  const raw = await req.text();
  new Webhook("<whsec_...>").verify(raw, Object.fromEntries(req.headers));
  const event = JSON.parse(raw);  // type == email.received
  ...  // download event.body_url
  return new Response(null, { status: 204 });
}
"""


BRANDS = [
    {"name": "Henkel"},
    {"name": "Porsche"},
    {"name": "Thermondo"},
    {"name": "Fizard"},
    {"name": "voiio"},
    {"name": "Sparkasse"},
]

TESTIMONIALS = [
    {
        "quote": "Sample endorsement. relay collects real quotes from friends in tech before launch.",
        "name": "Sample Supporter",
        "initials": "SS",
        "role": "Founder, Sample Company",
    },
    {
        "quote": "Sample endorsement. Replace this card with a real quote from the open-source community.",
        "name": "Sample Maintainer",
        "initials": "SM",
        "role": "Maintainer, Sample Project",
    },
    {
        "quote": "Sample endorsement. relay asks its friends in tech for honest feedback, not marketing copy.",
        "name": "Sample Engineer",
        "initials": "SE",
        "role": "Staff Engineer, Sample Corp",
    },
]


class HomeView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render the marketing landing page."""

    template_name = "start.html"
    title = _("Home")
    cache_control = {"public": True, "max_age": 300}

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "brands": BRANDS,
            "testimonials": TESTIMONIALS,
            "python_snippet": PYTHON_SNIPPET,
            "typescript_snippet": TYPESCRIPT_SNIPPET,
            "free_monthly_messages": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "price_per_1000_messages": settings.RELAY_PRICE_PER_1000_MESSAGES,
        }


class OpenSourceView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render the open-source pledge."""

    template_name = "open_source.html"
    title = _("the open-source pledge")
    parent = "home"
    cache_control = {"public": True, "max_age": 300}
