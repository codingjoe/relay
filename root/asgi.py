import os

from django.core.asgi import get_asgi_application
from django_esm import asgi

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

application = asgi.ESM(get_asgi_application())
