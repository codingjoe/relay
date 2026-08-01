from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from accounts.views import OrganizationScopedView

from .models import Message


class ContactMessagesView(OrganizationScopedView, ListView):
    """Merged timeline of inbound and outbound messages."""

    template_name = "tx_mail/contact_messages.html"
    context_object_name = "messages"
    paginate_by = 50
    title = _("Messages")
    parent = "accounts:org-home"

    class Direction:
        ALL = "all"
        SENT = "sent"
        RECEIVED = "received"

        CHOICES = (ALL, SENT, RECEIVED)

    def get_queryset(self):
        qs = Message.objects.filter(org=self.org).select_related(
            "outgoingmessage",
            "incomingmessage",
            "content_type",
        )
        direction = self.request.GET.get("direction", self.Direction.ALL)
        match direction:
            case self.Direction.SENT:
                qs = qs.filter(content_type__model="outgoingmessage")
            case self.Direction.RECEIVED:
                qs = qs.filter(content_type__model="incomingmessage")
        if email := self.request.GET.get("email"):
            qs = qs.filter(Q(mail_from__icontains=email) | Q(rcpt_to__icontains=email))
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "direction": self.request.GET.get("direction", self.Direction.ALL),
            "email": self.request.GET.get("email", ""),
        }
