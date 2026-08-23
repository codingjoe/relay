"""Add organization context for the navbar switcher."""


def organizations(request):
    """Expose the current org and the user's organizations to templates.

    `OrganizationScopedView` sets `current_org` on the request. On non-org
    pages, nothing is added to the context because the org switcher only
    appears when an org is active.
    """
    user = getattr(request, "user", None)
    current_org = getattr(request, "current_org", None)
    if getattr(user, "is_authenticated", False) and current_org is not None:
        return {
            "user_orgs": user.organizations.all(),
            "current_org": current_org,
        }
    return {}
