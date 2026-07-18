"""Root project views."""

from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "start.html"

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
        }
