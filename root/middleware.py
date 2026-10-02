from django_esm.conf import get_settings
from whitenoise.middleware import WhiteNoiseMiddleware


class EsmMiddleware(WhiteNoiseMiddleware):
    """
    Serve the django-esm module directory at `/esm/`.

    django-esm ships a WSGI wrapper for this, but relay serves Granian over
    ASGI. The WhiteNoise middleware covers both protocols and marks the
    content-hashed modules as immutable.
    """

    def __init__(self, get_response=None):
        config = get_settings()
        self.esm_prefix = f"/{config.STATIC_PREFIX.strip('/')}/"
        super().__init__(get_response)
        self.add_files(config.STATIC_DIR, prefix=config.STATIC_PREFIX)

    def immutable_file_test(self, path, url):
        if url.startswith(self.esm_prefix):
            return True
        return super().immutable_file_test(path, url)
