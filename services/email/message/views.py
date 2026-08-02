from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from accounts.views import OrganizationScopedView

from .models import Message


class ContactMessagesView(OrganizationScopedView, ListView):
    """Merged timeline of inbound and outbound messages."""

    template_name = "message/contact_messages.html"
    context_object_name = "messages"
    paginate_by = 50
    title = _("Messages")
    parent = "accounts:org-home"

    class Direction:
        ALL = "all"
        SENT = "sent"
        RECEIVED = "received"

        CHOICES = (ALL, SENT, RECEIVED)

    STATUS_BADGES = {
        "pending": "outline",
        "sent": "primary",
        "delivered": "primary",
        "held": "outline",
        "bounced": "destructive",
        "dropped": "destructive",
        "failed": "destructive",
        "received": "primary",
        "webhook_sent": "outline",
        "webhook_failed": "destructive",
        "retry": "outline",
    }

    STATUS_CHOICES = (
        ("pending", _("pending")),
        ("sent", _("sent")),
        ("delivered", _("delivered")),
        ("held", _("held")),
        ("bounced", _("bounced")),
        ("dropped", _("dropped")),
        ("failed", _("failed")),
        ("received", _("received")),
        ("webhook_sent", _("webhook sent")),
        ("webhook_failed", _("webhook failed")),
        ("retry", _("retry")),
    )

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
        if status := self.request.GET.get("status"):
            qs = qs.filter(
                Q(outgoingmessage__status=status) | Q(incomingmessage__status=status)
            )
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "direction": self.request.GET.get("direction", self.Direction.ALL),
            "email": self.request.GET.get("email", ""),
            "status": self.request.GET.get("status", ""),
            "status_badges": self.STATUS_BADGES,
            "status_choices": self.STATUS_CHOICES,
        }
