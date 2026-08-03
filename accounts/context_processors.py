"""Template context processors."""

from django.conf import settings


def organizations(request):
    """Expose the user's organizations and the current org to every template.

    `OrganizationScopedView` sets `current_org` on the request. On non-org
    pages, `current_org` is absent.

    Checks the session cookie before touching ``request.user`` so anonymous
    visitors never trigger session access or DB I/O.
    """
    if not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
        return {}
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "user_orgs": request.user.organizations.all(),
        "current_org": getattr(request, "current_org", None),
    }
