from django.apps import AppConfig


class NewsletterConfig(AppConfig):
    """Announce each published station log to the members who want it."""

    name = "services.email.newsletter"
    default_auto_field = "django.db.models.BigAutoField"
