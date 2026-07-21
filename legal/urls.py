from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    path("imprint/", views.ImprintView.as_view(), name="imprint"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
]
