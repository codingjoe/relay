"""Template context processors."""


def organizations(request):
    """Expose the user's organizations and the current org to every template.

    `OrganizationScopedView` sets `current_org` on the request. On non-org
    pages, `current_org` is absent.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "user_orgs": request.user.organizations.all(),
        "current_org": getattr(request, "current_org", None),
    }
