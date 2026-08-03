from django.urls import path

from . import views

app_name = "message"

urlpatterns = [
    path(
        "messages/",
        views.MessageListView.as_view(),
        name="message-list",
    ),
]
