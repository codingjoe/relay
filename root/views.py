import datetime

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import BreadcrumbViewMixin, CacheControlMixin

# Wordmarks of companies that back relay, with owner-attested endorsement.
# Optional keys: "url" (endorser link) and "logo" (static image path).

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
        "quote": "The sandbox is a killer feature. It lets us build faster and better without any infrastructure friction. You just flip a switch, lean back and watch it work.",
        "name": "Rustem Saiargaliev",
        "initials": "AM",
        "role": "Lead Engineer",
        "image": "/static/img/testimonials/rustem-saiargaliev.png",
    },
    {
        "quote": "As a founder, I need tools that get out of the way. We plug relay into any agentic workflow to get immediate access to sending and receiving messages.",
        "name": "Marc Metz",
        "initials": "MM",
        "role": "AI Entrepreneur (YC-W21)",
        "image": "/static/img/testimonials/marc-metz.jpeg",
    },
    {
        "quote": "In marketing, sender reputation is everything. relay ensures our emails actually hit the inbox instead of ending up in spam or on a block list, which is critical for any growing brand.",
        "name": "Sebastian Schirmer",
        "initials": "BS",
        "role": "Marketing Manager",
        "image": "/static/img/testimonials/sebasitan-schirmer.jpeg",
    },
]


class HomeView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render the marketing landing page."""

    template_name = "start.html"
    title = _("Home")
    cache_control = {"public": True, "max_age": datetime.timedelta(minutes=1)}

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "brands": BRANDS,
            "testimonials": TESTIMONIALS,
            "free_monthly_messages": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "price_per_1000_messages": settings.RELAY_PRICE_PER_1000_MESSAGES,
        }


class OpenSourceView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render the open-source pledge."""

    template_name = "open_source.html"
    title = _("the open-source pledge")
    parent = "home"
    cache_control = {"public": True, "max_age": datetime.timedelta(minutes=1)}
