import importlib.util
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.py"
SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


def load_settings(monkeypatch, **environment):
    """Return a fresh execution of root/settings.py under the given environment."""
    for name, value in environment.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("settings_under_test", SETTINGS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEmailURL:
    def test_load__empty_email_url_falls_back_to_console(self, monkeypatch):
        module = load_settings(monkeypatch, EMAIL_URL="", DEBUG=None, TEST=None)

        assert module.MAILERS["default"] == {
            "BACKEND": CONSOLE_BACKEND,
            "OPTIONS": {},
        }

    def test_load__unset_email_url_falls_back_to_console(self, monkeypatch):
        module = load_settings(monkeypatch, EMAIL_URL=None, DEBUG=None, TEST=None)

        assert module.MAILERS["default"] == {
            "BACKEND": CONSOLE_BACKEND,
            "OPTIONS": {},
        }

    def test_load__configured_email_url_wins(self, monkeypatch):
        module = load_settings(
            monkeypatch,
            EMAIL_URL="smtp://mail.example.com:2525",
            DEBUG=None,
            TEST=None,
        )

        assert module.MAILERS["default"] == {
            "BACKEND": SMTP_BACKEND,
            "OPTIONS": {"host": "mail.example.com", "port": 2525},
        }
