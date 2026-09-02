from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from kms.models import CERTIFICATE_CHAIN_MAX_DEPTH, Certificate

from .models import Message


class MessageListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
    """Display a merged timeline of inbound and outbound messages."""

    context_object_name = "messages"
    paginate_by = 50
    title = _("Email messages")
    parent = "accounts:org-home"

    class Direction(models.TextChoices):
        ALL = "all", _("all")
        SENT = "sent", _("sent")
        RECEIVED = "received", _("received")

    def get_queryset(self):
        qs = Message.objects.filter(org=self.org).select_related(
            "org",
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
        email = self.request.GET.get("email", "")
        status = self.request.GET.get("status", "")
        direction = self.request.GET.get("direction", self.Direction.ALL)
        filter_count = sum(
            bool(value) for value in (email, status, direction != self.Direction.ALL)
        )
        try:
            direction_label = self.Direction(direction).label
        except ValueError:
            direction_label = self.Direction.ALL.label
        return super().get_context_data(**kwargs) | {
            "direction": direction,
            "email": email,
            "status": status,
            "status_choices": Message.status_choices(),
            "filter_count": filter_count,
            "direction_label": direction_label,
        }


class MessageBreadcrumbMixin:
    """Title the breadcrumb crumb of a message detail view with its subject."""

    def get_breadcrumbs(self):
        breadcrumbs = super().get_breadcrumbs()
        breadcrumbs[0]["title"] = self.object.subject or str(self.object)
        return breadcrumbs


class CertificateDetailView(
    OrganizationScopedView, NoStoreCacheMixin, generic.DetailView
):
    """Display the X.509 metadata of a certificate a server presented."""

    context_object_name = "certificate"
    template_name = "message/certificate_detail.html"
    title = _("Certificate")
    parent = "message:message-list"
    pk_url_kwarg = "fingerprint"

    def get_queryset(self):
        fingerprints = set(
            Certificate.objects.filter(
                Q(incoming_messages__org=self.org)
                | Q(transmissions__message__org=self.org)
            ).values_list("fingerprint", flat=True)
        )
        level = fingerprints
        for _depth in range(CERTIFICATE_CHAIN_MAX_DEPTH):
            level = set(
                Certificate.objects.filter(
                    issued_certificates__fingerprint__in=level
                ).values_list("fingerprint", flat=True)
            )
            if not (level - fingerprints):
                break
            fingerprints |= level
        return Certificate.objects.filter(fingerprint__in=fingerprints)
