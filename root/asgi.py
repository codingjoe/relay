import os

from django.core.asgi import get_asgi_application
from django_esm import asgi
from granian.utils.proxies import wrap_asgi_with_proxy_headers

from abstract.proxy import get_trusted_proxy_hosts

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings")

application = wrap_asgi_with_proxy_headers(
    asgi.ESM(get_asgi_application()),
    trusted_hosts=get_trusted_proxy_hosts(),
)
