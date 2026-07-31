from django.apps import AppConfig


class TxMailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tx_mail"
    verbose_name = "Transactional mail"
