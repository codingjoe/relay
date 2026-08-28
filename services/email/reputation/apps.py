from django.apps import AppConfig


class ReputationConfig(AppConfig):
    name = "services.email.reputation"

    def ready(self):
        from . import signals  # noqa: F401
