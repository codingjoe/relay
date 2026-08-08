from django.apps import AppConfig


class DomainsConfig(AppConfig):
    name = "domains"

    def ready(self):
        from . import (
            checks,  # noqa: F401
            signals,  # noqa: F401
        )
