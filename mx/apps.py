from django.apps import AppConfig


class MxConfig(AppConfig):
    name = "mx"

    def ready(self):
        from . import signals  # noqa: F401
