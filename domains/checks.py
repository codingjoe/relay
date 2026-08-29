import dns.resolver
from django.conf import settings
from django.core.checks import Error, Warning, register
from django.db.utils import DatabaseError

from .models import Domain


@register()
def check_platform_domain(app_configs, **kwargs):
    """Warn when relay is missing a flagged platform domain or its DKIM keys."""
    warnings = []
    try:
        platform_domain = Domain.objects.select_related(
            "dkim_key_rsa2048",
            "dkim_key_rsa1024",
            "dkim_key_ed25519",
        ).get(is_platform=True)
    except Domain.DoesNotExist:
        warnings.append(
            Warning(
                "No domain is flagged as the platform identity, so relay does "
                "not cosign outgoing mail with the platform identity or "
                "publish its DKIM records. Flag the platform domain.",
                hint="Set is_platform on the Domain named RELAY_PLATFORM_DOMAIN.",
                id="domains.W001",
            )
        )
    except DatabaseError:
        return warnings
    else:
        missing = [
            name
            for name in (
                "dkim_key_rsa2048",
                "dkim_key_rsa1024",
                "dkim_key_ed25519",
            )
            if getattr(platform_domain, f"{name}_id") is None
        ]
        if missing:
            warnings.append(
                Warning(
                    f"The platform domain {platform_domain.name} is missing DKIM "
                    f"keys ({', '.join(missing)}), so relay cosigns outgoing mail "
                    "only with the configured ciphers and does not publish the "
                    "missing DKIM TXT records. Generate the DKIM signing keys "
                    "for the platform domain.",
                    obj=platform_domain,
                    id="domains.W002",
                )
            )
    return warnings


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
    except dns.exception.DNSException as error:
        errors.append(
            Error(
                f"Could not resolve NS records for {managed_zone}: {error}.",
                hint="Delegate the managed sender domain zone to the relay nameservers.",
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
                hint="Delegate the managed sender domain zone to the relay nameservers.",
                id="domains.E003",
            )
        )

    return errors
