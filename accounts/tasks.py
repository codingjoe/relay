import logging
from datetime import timedelta

from django.conf import settings
from django.tasks import task
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from threadmill.retry import ExponentialBackoff

from .models import EmailVerification

logger = logging.getLogger(__name__)


@task(
    retry=ExponentialBackoff(
        base_delay=timedelta(seconds=1),
        max_delay=timedelta(minutes=5),
        max_retries=5,
        expected_exceptions=(OSError,),
    )
)
def send_verification_email(email_verification_id):
    """Email the account holder a link to verify their email address."""
    verification = EmailVerification.objects.select_related("user").get(
        pk=email_verification_id
    )
    if verification.verified_at is None:
        scheme = "http" if settings.DEBUG or settings.TEST else "https"
        verify_url = (
            f"{scheme}://{settings.RELAY_PLATFORM_DOMAIN}"
            f"{reverse('accounts:email-verify', kwargs={'token': verification.generate_token()})}"
        )
        body = render_to_string(
            "accounts/email_verification_email.txt",
            {
                "username": verification.user.username,
                "verify_url": verify_url,
            },
        )
        verification.user.email_user(
            subject=_("Verify your email address"),
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
        )
