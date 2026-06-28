from django.urls import path
from django.views import generic
from django.views.decorators.cache import cache_page

from . import views

app_name = "sponsors"
urlpatterns = [
    path(
        "",
        generic.TemplateView.as_view(template_name="sponsors/index.html"),
        name="index",
    ),
    path(
        "<owner>/<repo>.svg",
        cache_page(views.SponsorshipView.TTL)(views.SponsorshipView.as_view()),
        name="sponsors",
    ),
    path(
        "<owner>/<repo>",
        cache_page(views.SponsorshipView.TTL)(views.SponsorshipView.as_view()),
        name="sponsors_no_ext",
    ),
]
