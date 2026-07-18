"""URL configuration for legal pages."""

from django.urls import path

from .views import ImprintView, PrivacyView, TermsView

app_name = "legal"

urlpatterns = [
    path("imprint/", ImprintView.as_view(), name="imprint"),
    path("terms/", TermsView.as_view(), name="terms"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
]
