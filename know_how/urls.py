from django.urls import path

from . import views

app_name = "know_how"

urlpatterns = [
    path("", views.KnowHowListView.as_view(), name="list"),
    path("<slug:slug>/", views.KnowHowDetailView.as_view(), name="detail"),
]
