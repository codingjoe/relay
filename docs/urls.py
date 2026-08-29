from django.urls import path

from . import views

app_name = "docs"

urlpatterns = [
    path("", views.DocsListView.as_view(), name="list"),
    path("<slug:slug>/", views.DocsDetailView.as_view(), name="detail"),
]
