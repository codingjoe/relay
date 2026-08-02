from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from accounts.views import OrganizationScopedView
from services.email.mx.models import IncomingMessage
from services.email.smtp.models import OutgoingMessage

from .models import Message


class ContactMessagesView(OrganizationScopedView, ListView):
    """Merged timeline of inbound and outbound messages."""

    template_name = "message/contact_messages.html"
    context_object_name = "messages"
    paginate_by = 50
    title = _("Messages")
    parent = "accounts:org-home"

    class Direction(models.TextChoices):
        ALL = "all", _("all")
        SENT = "sent", _("sent")
        RECEIVED = "received", _("received")

    class StatusChoices(models.TextChoices):
        """Union of :class:`OutgoingMessage.Status` and :class:`IncomingMessage.Status`."""

        PENDING = OutgoingMessage.Status.PENDING, _("pending")
        SENT = OutgoingMessage.Status.SENT, _("sent")
        DELIVERED = OutgoingMessage.Status.DELIVERED, _("delivered")
        HELD = OutgoingMessage.Status.HELD, _("held")
        BOUNCED = OutgoingMessage.Status.BOUNCED, _("bounced")
        DROPPED = OutgoingMessage.Status.DROPPED, _("dropped")
        FAILED = OutgoingMessage.Status.FAILED, _("failed")
        RECEIVED = IncomingMessage.Status.RECEIVED, _("received")
        WEBHOOK_SENT = IncomingMessage.Status.WEBHOOK_SENT, _("webhook sent")
        WEBHOOK_FAILED = IncomingMessage.Status.WEBHOOK_FAILED, _("webhook failed")

    STATUS_BADGES = {
        StatusChoices.PENDING: "outline",
        StatusChoices.SENT: "primary",
        StatusChoices.DELIVERED: "primary",
        StatusChoices.HELD: "outline",
        StatusChoices.BOUNCED: "destructive",
        StatusChoices.DROPPED: "destructive",
        StatusChoices.FAILED: "destructive",
        StatusChoices.RECEIVED: "primary",
        StatusChoices.WEBHOOK_SENT: "outline",
        StatusChoices.WEBHOOK_FAILED: "destructive",
    }

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
            "status_choices": self.StatusChoices.choices,
        }
