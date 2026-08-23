"""Add organization context for the navbar switcher."""


def organizations(request):
    """Expose the current org and the user's organizations to templates.

    `OrganizationScopedView` sets `current_org` on the request. On non-org
    pages, nothing is added to the context because the org switcher only
    appears when an org is active.
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {}
    current_org = getattr(request, "current_org", None)
    if current_org is None:
        return {}
    return {
        "user_orgs": user.organizations.all(),
        "current_org": current_org,
    }
