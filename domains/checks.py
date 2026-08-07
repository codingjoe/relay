import dns.resolver
from django.conf import settings
from django.core.checks import Error, register


@register("domains", deploy=True)
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
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout) as e:
        errors.append(
            Error(
                f"Could not resolve NS records for {managed_zone}: {e}.",
                hint="Delegate the managed sender domain zone to Relay's nameservers.",
                id="domains.E002",
            )
        )
        return errors

    our_ns = {ns.rstrip(".").lower() for ns in settings.RELAY_DNS_NS_NAMESERVERS}
    their_ns = {str(r.target).rstrip(".").lower() for r in ns_records}
    if our_ns != their_ns:
        errors.append(
            Error(
                f"NS delegation for {managed_zone} does not match "
                f"RELAY_DNS_NS_NAMESERVERS. Expected: {our_ns}. "
                f"Found: {their_ns}.",
                hint="Delegate the managed sender domain zone to Relay's nameservers.",
                id="domains.E003",
            )
        )

    return errors
