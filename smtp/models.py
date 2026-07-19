"""SMTP credential model — concrete implementation of accounts.Credential."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Credential


class SmtpCredential(Credential):
    class Type(models.TextChoices):
        SMTP = "smtp", _("SMTP")
        SMTP_IP = "smtp-ip", _("SMTP-IP")

    type = models.CharField(
        _("type"),
        max_length=7,
        choices=Type.choices,
        default=Type.SMTP,
        help_text=_("SMTP authentication method."),
    )
