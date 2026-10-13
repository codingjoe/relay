"""Hand Django's per-request connection cleanup to every thread an MCP request uses."""

from typing import Any

from anyio.to_thread import run_sync
from asgiref.sync import sync_to_async
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


class DjangoRequestSignalsMiddleware(Middleware):
    """
    Run Django's request signals, and its connection cleanup, around each request.

    Django ties `close_old_connections` to both signals and keeps its
    connections per thread, so the signals go through the threadpool a sync body
    runs in rather than the event loop. Code that reaches for `sync_to_async`,
    as the access token dependency does, runs on asgiref's own sync thread
    instead, which no signal reaches, so that thread is cleaned directly. The
    pool keeps its idle worker while requests run one at a time, but a busy pool
    may signal a sibling thread.
    """

    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        await run_sync(request_started.send, type(self))
        try:
            return await call_next(context)
        finally:
            await run_sync(request_finished.send, type(self))
            await sync_to_async(close_old_connections)()
