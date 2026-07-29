from django.apps import AppConfig


class AbstractConfig(AppConfig):
    name = "abstract"

    def ready(self):
        from . import checks  # noqa: F401
