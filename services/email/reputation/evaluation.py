from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from services.email.msa.models import OutgoingMessage, Transmission

from .models import FblReport


def compute_domain_reputation(domain):
    """Return bounce and complaint rates for a domain over the rolling window.

    Returns a dict with keys: `total_sent`, `hard_bounces`,
    `soft_bounces`, `complaints`, `hard_bounce_rate`,
    `soft_bounce_rate`, `complaint_rate`, `bounce_rate`.
    Rates are floats (0.0-1.0). Returns zero counts and rates when
    the domain has no outgoing messages in the window.
    """
    window_start = timezone.now() - timedelta(
        days=settings.RELAY_REPUTATION_WINDOW_DAYS
    )
    total_sent = OutgoingMessage.objects.filter(
        domain=domain,
        created_at__gte=window_start,
    ).count()

    transmissions = Transmission.objects.filter(
        message__domain=domain,
        message__created_at__gte=window_start,
        status=Transmission.Status.BOUNCED,
    )
    hard_bounces = transmissions.filter(code__gte=500).count()
    soft_bounces = transmissions.filter(code__lt=500).count()

    complaints = FblReport.objects.filter(
        domain=domain,
        created_at__gte=window_start,
    ).count()

    bounce_rate = (hard_bounces + soft_bounces) / total_sent if total_sent else 0.0
    hard_bounce_rate = hard_bounces / total_sent if total_sent else 0.0
    soft_bounce_rate = soft_bounces / total_sent if total_sent else 0.0
    complaint_rate = complaints / total_sent if total_sent else 0.0

    return {
        "total_sent": total_sent,
        "hard_bounces": hard_bounces,
        "soft_bounces": soft_bounces,
        "complaints": complaints,
        "bounce_rate": bounce_rate,
        "hard_bounce_rate": hard_bounce_rate,
        "soft_bounce_rate": soft_bounce_rate,
        "complaint_rate": complaint_rate,
    }


def check_domain_reputation(domain):
    """Evaluate bounce and complaint rates and set or clear the reputation hold.

    Sets `reputation_hold=True` when bounce rate or complaint rate
    exceeds the configured thresholds and the domain has sent at least
    `RELAY_REPUTATION_MIN_VOLUME` messages in the window. Clears the
    hold when rates have recovered.

    Returns the computed reputation dict.
    """
    stats = compute_domain_reputation(domain)
    if stats["total_sent"] < settings.RELAY_REPUTATION_MIN_VOLUME:
        return stats

    exceeds = (
        stats["bounce_rate"] > settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD
        or stats["complaint_rate"] > settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD
    )

    if exceeds and not domain.reputation_hold:
        domain.reputation_hold = True
        domain.reputation_hold_at = timezone.now()
        domain.save(
            update_fields=["reputation_hold", "reputation_hold_at", "modified_at"]
        )
    elif not exceeds and domain.reputation_hold:
        domain.reputation_hold = False
        domain.reputation_hold_at = None
        domain.save(
            update_fields=["reputation_hold", "reputation_hold_at", "modified_at"]
        )

    return stats
