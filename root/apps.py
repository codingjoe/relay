import multiprocessing

from django.apps import AppConfig
from pythonjsonlogger.json import JsonFormatter


class RootConfig(AppConfig):
    name = "root"

    def ready(self):
        # threadmill.executor attaches a plain-text handler to the
        # multiprocessing logger at import time, which happens during
        # threadmill's AppConfig.ready(), before this one. Without this,
        # threadmill's task lifecycle lines and the atexit
        # "process shutting down" line of every service process would
        # be emitted twice: once as JSON and once as plain text.
        logger = multiprocessing.get_logger()
        json_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler.formatter, JsonFormatter)
        ]
        if json_handlers:
            logger.handlers = json_handlers
