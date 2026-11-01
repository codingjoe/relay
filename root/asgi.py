import os

from django.conf import settings
from django.core.asgi import get_asgi_application
from django_esm import asgi
from granian.utils.proxies import wrap_asgi_with_proxy_headers

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

application = wrap_asgi_with_proxy_headers(
    asgi.ESM(get_asgi_application()),
    trusted_hosts=settings.TRUSTED_PROXY_HOSTS,
)
