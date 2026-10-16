from .onboarding import get_email_context


def onboarding_context(request):
    """Expose the first-steps state and the sending domains to the layout."""
    if org := getattr(request, "current_org", None):
        return get_email_context(org, request)
    return {}
