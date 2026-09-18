from .onboarding import is_onboarding_complete


def onboarding_context(request):
    """Expose the first-steps state to the shared layout."""
    if org := getattr(request, "current_org", None):
        return {"onboarding_complete": is_onboarding_complete(org)}
    return {}
