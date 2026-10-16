# settings.py
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.relay.example.com",
            "port": 465,
            "use_ssl": True,
            "username": "acme",
            "password": "<credential key>",
        },
    },
}

# send from anywhere
from django.core.mail import send_mail

send_mail("Invoice 42", "Attached.", "billing@acme.com", ["kim@example.net"])
