import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import translation
from django_letter.exceptions import InactiveUserError, MissingEmailError

from accounts.models import Organization
from domains.models import Domain
from services.email.msa import emails


@pytest.fixture
def base_url(settings):
    """Return the host the package derives the base URL from."""
    settings.ALLOWED_HOSTS = ["relay.example"]
    return "https://relay.example"


def make_test_email(*, domain=None, user=None, **kwargs):
    kwargs.setdefault("language", translation.get_language())
    return emails.TestEmail.to_user(
        user or User(email="member@acme.example"),
        domain=domain or Domain(name="acme.example", org=Organization(slug="acme")),
        **kwargs,
    )


class TestTestEmail:
    def test_get_context_data__builds_sender_and_dashboard_url(self, base_url):
        user = User(email="member@acme.example")
        email = make_test_email(user=user)
        assert email.get_context_data() == {
            "user": user,
            "domain": "acme.example",
            "sender": f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example",
            "recipient": "member@acme.example",
            "dashboard_url": f"{base_url}/org/acme/email/messages/",
        }

    def test_get_context_data__strips_a_trailing_slash(self):
        email = make_test_email(base_url="https://acme.example/")
        assert (
            email.get_context_data()["dashboard_url"]
            == "https://acme.example/org/acme/email/messages/"
        )

    def test_init__uses_the_active_language(self):
        email = make_test_email()
        assert email.language == translation.get_language()

    def test_init__leaves_base_url_to_the_package(self, base_url):
        email = make_test_email()
        assert email.get_base_url() == base_url

    def test_init__arguments_win(self):
        email = make_test_email(language="de", base_url="https://mail.example.org")
        assert email.language == "de"
        assert email.get_base_url() == "https://mail.example.org"

    def test_to_user__addresses_the_member_with_the_display_name(self):
        email = make_test_email(
            user=User(
                email="member@acme.example",
                first_name="Alice",
                last_name="Example",
            )
        )
        assert email.to == ["Alice Example <member@acme.example>"]

    def test_to_user__rejects_inactive_account(self):
        with pytest.raises(InactiveUserError):
            make_test_email(user=User(email="member@acme.example", is_active=False))

    def test_to_user__rejects_account_without_address(self):
        with pytest.raises(MissingEmailError):
            make_test_email(user=User(email=""))

    def test_message__interpolates_domain_into_subject(self):
        email = make_test_email(
            domain=Domain(name="custom.example", org=Organization(slug="custom"))
        )
        assert email.message()["Subject"] == "Test email from custom.example"

    def test_message__attaches_html_and_plain_text_parts(self):
        message = make_test_email().message()
        assert [part.get_content_type() for part in message.iter_parts()] == [
            "text/plain",
            "text/html",
        ]

    def test_message__plain_text_derives_from_html(self, base_url):
        message = make_test_email().message()
        html = message.get_body(preferencelist=("html",)).get_content()
        text = message.get_body(preferencelist=("plain",)).get_content()
        assert f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example" in html
        assert f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example" in text
        assert "member@acme.example" in text
        link = f"{base_url}/org/acme/email/messages/"
        assert f'href="{link}"' in html
        assert f"<{link}>" in text

    def test_render_preview__renders_without_arguments(self, base_url):
        email = emails.TestEmail.render_preview()
        assert email.subject == "Test email from acme.example"
        assert f'<html lang="{settings.LANGUAGE_CODE}">' in email.html
        assert "member@acme.example" in email.body
        assert f"{base_url}/org/acme/email/messages/" in email.body
        assert f'<img src="{base_url}/static/img/word-brand-512x' in email.html

    def test_render_preview__uses_given_domain_and_recipient(self):
        email = emails.TestEmail.render_preview(
            domain=Domain(name="custom.example", org=Organization(slug="custom")),
            extra_context={"user": User(email="member@custom.example")},
        )
        assert email.subject == "Test email from custom.example"
        assert "member@custom.example" in email.html

    def test_render_preview__language_argument_wins(self):
        email = emails.TestEmail.render_preview(language="de")
        assert email.language == "de"
        assert '<html lang="de">' in email.html
