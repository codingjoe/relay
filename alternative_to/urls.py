from django.urls import path

from . import views

app_name = "alternative_to"

urlpatterns = [
    path("", views.AlternativeToListView.as_view(), name="list"),
    path("<slug:slug>/", views.AlternativeToDetailView.as_view(), name="detail"),
]
