import dns.resolver
from django.conf import settings
from django.core.checks import Error, Warning, register
from django.db.utils import OperationalError, ProgrammingError

from .models import Domain


@register()
def check_managed_domain_dns(app_configs, **kwargs):
    """Verify that DNS records for the managed sender domain zone are configured."""
    errors = []
    managed_zone = settings.RELAY_MANAGED_SENDER_DOMAIN

    if not managed_zone:
        errors.append(
            Error(
                "RELAY_MANAGED_SENDER_DOMAIN is not set.",
                hint="Set RELAY_MANAGED_SENDER_DOMAIN in settings to configure "
                "the managed sender domain zone.",
                id="domains.E001",
            )
        )
        return errors

    # Check NS delegation for the managed domain zone
    try:
        ns_records = dns.resolver.resolve(managed_zone, "NS")
        our_ns = {ns.rstrip(".").lower() for ns in settings.RELAY_DNS_NS_NAMESERVERS}
        their_ns = {str(r.target).rstrip(".").lower() for r in ns_records}
        if our_ns != their_ns:
            errors.append(
                Warning(
                    f"NS delegation for {managed_zone} does not match "
                    f"RELAY_DNS_NS_NAMESERVERS. Expected: {our_ns}. "
                    f"Found: {their_ns}.",
                    hint="Delegate the managed sender domain zone to Relay's "
                    "nameservers.",
                    id="domains.W001",
                )
            )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        errors.append(
            Warning(
                f"Could not resolve NS records for {managed_zone}.",
                hint="Delegate the managed sender domain zone to Relay's nameservers.",
                id="domains.W002",
            )
        )

    # Check that managed domains in the database have all DNS statuses set to OK
    try:
        managed_domains = list(Domain.objects.filter(is_managed=True))
    except OperationalError, ProgrammingError:
        return errors

    for domain in managed_domains:
        status_fields = [
            "nameserver_status",
            "spf_status",
            "dkim_status",
            "dmarc_status",
            "mta_sts_status",
            "tls_rpt_status",
        ]
        for field in status_fields:
            if getattr(domain, field) != Domain.Status.OK:
                errors.append(
                    Warning(
                        f"Managed domain {domain.name} has {field} = "
                        f"{getattr(domain, field)}. Expected OK.",
                        hint="Run the DNS verification or check the nameserver "
                        "configuration.",
                        id="domains.W003",
                    )
                )
        if not domain.is_verified:
            errors.append(
                Warning(
                    f"Managed domain {domain.name} is not verified.",
                    hint="Managed domains should be pre-verified.",
                    id="domains.W004",
                )
            )

    return errors
