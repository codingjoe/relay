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
        }


class OpenSourceView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render the open-source pledge."""

    template_name = "open_source.html"
    title = _("the open-source pledge")
    parent = "home"
    cache_control = {"public": True, "max_age": 300}
