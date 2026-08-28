"""Admin app configuration."""

from importlib import import_module

from django.apps import apps
from django.contrib.admin.apps import AdminConfig, SimpleAdminConfig
from django.utils.module_loading import module_has_submodule


class RelayAdminConfig(AdminConfig):
    """Admin autodiscovery that skips social_django's admin module.

    social_django's `admin` module sets `list_select_related = True`, which
    Django 6 deprecates at class definition, so importing it emits a
    `RemovedInDjango70Warning` on every startup. The admin classes are
    re-registered in `accounts.admin` with the recommended tuple instead.
    """

    def ready(self):
        # SimpleAdminConfig registers the admin checks; AdminConfig.ready()
        # additionally discovers every app's admin module, including social_django's.
        SimpleAdminConfig.ready(self)
        self.autodiscover()

    def autodiscover(self):
        for app_config in filter(self.discoverable, apps.get_app_configs()):
            if module_has_submodule(app_config.module, "admin"):
                import_module(f"{app_config.name}.admin")

    def discoverable(self, app_config):
        return app_config.name != "social_django"
