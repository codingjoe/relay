from django.urls import path

from . import views

app_name = "mcp"

urlpatterns = [
    path("", views.SetupView.as_view(), name="setup"),
]
