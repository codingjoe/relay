from datetime import timedelta
from typing import TypedDict

from django.conf import settings
from django.core.mail import mail_managers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Membership, Organization
from services.email.msa.models import OutgoingMessage, Transmission

from .models import FblReport


class ReputationStats(TypedDict):
    total_sent: int
    hard_bounces: int
    soft_bounces: int
    complaints: int
    hard_bounce_rate: float
    complaint_rate: float


def compute_org_reputation(org: Organization) -> ReputationStats:
    """Return bounce and complaint rates for an organization over the rolling window.

    Returns zero counts and rates when the organization has no outgoing
    messages in the window. Only SMTP 5xx bounces count toward the
    bounce rate; soft bounces are for display only.
    """
    window_start = timezone.now() - timedelta(
        days=settings.RELAY_REPUTATION_WINDOW_DAYS
    )
    total_sent = OutgoingMessage.objects.filter(
        org=org,
        created_at__gte=window_start,
    ).count()

    transmissions = Transmission.objects.filter(
        message__org=org,
        message__created_at__gte=window_start,
        status=Transmission.Status.BOUNCED,
    )
    hard_bounces = transmissions.filter(code__gte=500).count()
    soft_bounces = transmissions.filter(code__lt=500).count()

    complaints = (
        FblReport.objects.filter(
            org=org,
            created_at__gte=window_start,
            source=FblReport.Source.PROVIDER,
        ).count()
        + OutgoingMessage.objects.filter(
            org=org,
            created_at__gte=window_start,
            status=OutgoingMessage.Status.HELD,
        ).count()
    )

    hard_bounce_rate = hard_bounces / total_sent if total_sent else 0.0
    complaint_rate = complaints / total_sent if total_sent else 0.0

    return {
        "total_sent": total_sent,
        "hard_bounces": hard_bounces,
        "soft_bounces": soft_bounces,
        "complaints": complaints,
        "hard_bounce_rate": hard_bounce_rate,
        "complaint_rate": complaint_rate,
    }


def check_org_reputation(org: Organization) -> ReputationStats:
    """Evaluate rates and suspend the organization permanently on a
    threshold breach.

    Suspends the organization when the hard-bounce rate or complaint rate
    exceeds the configured thresholds and the organization has sent at
    least `RELAY_REPUTATION_MIN_VOLUME` messages in the window. The
    suspension is never cleared automatically. Returns the computed
    reputation stats.
    """
    stats = compute_org_reputation(org)
    if stats["total_sent"] < settings.RELAY_REPUTATION_MIN_VOLUME:
        return stats

    if not (
        stats["hard_bounce_rate"] > settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD
        or stats["complaint_rate"] > settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD
    ):
        return stats

    now = timezone.now()
    updated = Organization.objects.filter(pk=org.pk, suspended_at__isnull=True).update(
        suspended_at=now, modified_at=now
    )
    if updated:
        notify_org_locked(org, stats)
    return stats


def notify_org_locked(org: Organization, stats: ReputationStats) -> None:
    """Email the organization admins and platform staff about the suspension."""
    subject = _("Your account was suspended due to sender reputation")
    message = _(
        "Your organization was suspended because outgoing messages exceeded "
        "the bounce or complaint rate threshold. Bounces: %(hard_bounces)s, "
        "complaints: %(complaints)s, messages sent: %(total_sent)s over the "
        "last %(days)s days. New submissions are rejected and queued "
        "messages are dropped. Staff will review your account."
    ) % {
        "hard_bounces": stats["hard_bounces"],
        "complaints": stats["complaints"],
        "total_sent": stats["total_sent"],
        "days": settings.RELAY_REPUTATION_WINDOW_DAYS,
    }
    for membership in Membership.objects.filter(
        org=org,
        role=Membership.Role.ADMIN,
    ).select_related("user"):
        membership.user.email_user(
            subject, message, from_email=settings.DEFAULT_FROM_EMAIL
        )
    mail_managers(subject, message)
