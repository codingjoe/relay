from django.urls import path

from . import views

app_name = "captains_log"

urlpatterns = [
    path("", views.CaptainsLogListView.as_view(), name="list"),
    path("<slug:slug>/", views.CaptainsLogDetailView.as_view(), name="detail"),
    path(
        "<slug:slug>/images/<path:name>",
        views.CaptainsLogImageView.as_view(),
        name="image",
    ),
]
