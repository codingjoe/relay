import logging

from django.conf import settings
from django.tasks import task
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from .models import RecoveryEvent

logger = logging.getLogger(__name__)


@task
def notify_recovery_triggered(recovery_event_id):
    """Email all org members when a recovery event is logged."""
    event = RecoveryEvent.objects.select_related(
        "org_encryption_key__org", "triggered_by"
    ).get(pk=recovery_event_id)
    org = event.org_encryption_key.org
    memberships = org.memberships.email_verified().select_related("user")

    scheme = "http" if settings.DEBUG or settings.TEST else "https"
    org_url = f"{scheme}://{settings.RELAY_PLATFORM_DOMAIN}{org.get_absolute_url()}"

    context = {
        "org_slug": org.slug,
        "org_url": org_url,
        "triggered_by": str(event.triggered_by),
        "created_at": event.created_at.isoformat(),
    }
    body = render_to_string("kms/recovery_notification.txt", context)
    subject = _("Encryption recovery triggered for %(org)s") % {"org": org.slug}

    for membership in memberships:
        try:
            membership.user.email_user(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
            )
        except Exception:
            logger.exception(
                "Recovery notification to %s failed", membership.user.email
            )
