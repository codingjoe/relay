import importlib
from unittest import mock

import pytest
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

import root.settings


@pytest.fixture(autouse=True)
def restore_settings(monkeypatch):
    yield
    monkeypatch.undo()
    importlib.reload(root.settings)


def test_sentry_logging_integration__captures_stdlib_logs(monkeypatch):
    """Send stdlib log records to Sentry when a DSN is configured."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.setenv("TEST", "false")
    monkeypatch.setenv("DEBUG", "false")

    with mock.patch.object(sentry_sdk, "init") as init:
        importlib.reload(root.settings)

    init.assert_called_once()
    logging_integration = next(
        integration
        for integration in init.call_args.kwargs["integrations"]
        if isinstance(integration, LoggingIntegration)
    )
    assert logging_integration.capture_sentry_logs is True
