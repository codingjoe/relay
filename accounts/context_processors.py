"""Template context processors."""

from django.utils.functional import SimpleLazyObject

from .models import EmailVerification


def email_verification(request):
    """
    Expose whether the logged-in user's email address is unverified.

    `email_verification_pending` drives the banner that reminds users to
    open their verification link. Unverified users receive no
    security-sensitive mail. The flag is lazy: public pages that never
    render the banner stay free of session and database access.
    """

    def fetch_pending():
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return EmailVerification.objects.filter(
            user=user,
            verified_at__isnull=True,
        ).exists()

    return {"email_verification_pending": SimpleLazyObject(fetch_pending)}
