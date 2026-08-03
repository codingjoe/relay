"""Root project views."""

from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from abstract.views import BreadcrumbViewMixin, CacheControlMixin


class HomeView(CacheControlMixin, BreadcrumbViewMixin, TemplateView):
    """Marketing landing page for unauthenticated visitors."""

    template_name = "start.html"
    title = _("Home")
    cache_control = {"public": True, "max_age": 300}

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
        }
