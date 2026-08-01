from django.urls import path

from . import views

app_name = "message"

urlpatterns = [
    path(
        "contacts/messages/",
        views.ContactMessagesView.as_view(),
        name="contact-messages",
    ),
]
