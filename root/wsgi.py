import os

from django.core.wsgi import get_wsgi_application
from django_esm import wsgi

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

application = wsgi.ESM(get_wsgi_application())
