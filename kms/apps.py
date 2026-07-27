from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class KmsConfig(AppConfig):
    name = "kms"
    verbose_name = _("Key management")
