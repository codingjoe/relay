from django.urls import path

from . import views

app_name = "tx_mail"

urlpatterns = [
    path(
        "contacts/messages/",
        views.ContactMessagesView.as_view(),
        name="contact-messages",
    ),
    path(
        "contacts/reports/",
        views.ContactReportsView.as_view(),
        name="contact-reports",
    ),
]
