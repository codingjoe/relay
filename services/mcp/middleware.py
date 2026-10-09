"""Emit Django's request signals around every MCP request."""

from typing import Any

from anyio.to_thread import run_sync
from django.core.signals import request_finished, request_started
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


class DjangoRequestSignalsMiddleware(Middleware):
    """
    Hand Django's request signals to the thread an MCP body runs on.

    Django ties `close_old_connections` to both signals, and its receivers are
    thread local, so the signals must fire on the worker thread the body runs
    on rather than on the event loop. The pool keeps its idle worker on
    one-at-a-time requests, but a busy pool may signal a sibling thread.
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
