"""Template context processors."""

from django.conf import settings

from .models import EmailVerification


def organizations(request):
    """Expose the user's organizations and the current org to every template.

    `OrganizationScopedView` sets `current_org` on the request. On non-org
    pages, `current_org` is absent. `email_verification_pending` drives the
    banner that reminds users to open their verification link.
    """
    if not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
        return {}
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "user_orgs": request.user.organizations.all(),
        "current_org": getattr(request, "current_org", None),
        "email_verification_pending": EmailVerification.objects.filter(
            user=request.user,
            verified_at__isnull=True,
        ).exists(),
    }
