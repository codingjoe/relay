"""Run Django request signals and connection cleanup around each MCP request."""

import typing

from anyio.to_thread import run_sync
from asgiref.sync import sync_to_async
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


class DjangoRequestSignalsMiddleware(Middleware):
    """Run Django's request signals and connection cleanup around each request."""

    async def on_request(
        self,
        context: MiddlewareContext[typing.Any],
        call_next: CallNext[typing.Any, typing.Any],
    ) -> typing.Any:
        await run_sync(request_started.send, type(self))
        try:
            return await call_next(context)
        finally:
            await run_sync(request_finished.send, type(self))
            await sync_to_async(close_old_connections)()
