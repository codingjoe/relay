from django.contrib.auth.middleware import RemoteUserMiddleware


class HttpHeaderRemoteUserMiddleware(RemoteUserMiddleware):
    """Authenticate each request as `X-Remote-User`, falling back to `REMOTE_USER_NAME`. Registered only when DEBUG is True."""

    header = "HTTP_X_REMOTE_USER"
    REMOTE_USER_NAME = "test"
    force_logout_if_no_header = True

    def process_request(self, request):
        # An active hijack must not be reset by development auto-login.
        hijack_history = request.session.get("hijack_history")
        return None if hijack_history else super().process_request(request)

    async def aprocess_request(self, request):
        hijack_history = await request.session.aget("hijack_history")
        return None if hijack_history else await super().aprocess_request(request)

    def get_username(self, request):
        try:
            return request.META[self.header]
        except KeyError:
            return self.REMOTE_USER_NAME
