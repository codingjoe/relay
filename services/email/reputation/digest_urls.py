from django.urls import path

from . import views

app_name = "digest"

urlpatterns = [
    path("digest/<str:token>", views.DigestOptOutView.as_view(), name="opt-out"),
]
