from django.contrib.auth.middleware import RemoteUserMiddleware


class HttpHeaderRemoteUserMiddleware(RemoteUserMiddleware):
    """Authenticate each request as `X-Remote-User`, falling back to `REMOTE_USER_NAME`. Registered only when DEBUG is True."""

    header = "HTTP_X_REMOTE_USER"
    REMOTE_USER_NAME = "test"
    force_logout_if_no_header = True

    def get_username(self, request):
        try:
            return request.META[self.header]
        except KeyError:
            return self.REMOTE_USER_NAME
