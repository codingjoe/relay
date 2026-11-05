# settings.py
import os

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.relay.example.com",
            "port": 465,
            "use_ssl": True,
            "username": "acme",
            "password": os.environ["SMTP_PASSWORD"],
        },
    },
}

# send from anywhere
from django.core.mail import send_mail

send_mail("Invoice 42", "Attached.", "billing@acme.com", ["kim@example.net"])
