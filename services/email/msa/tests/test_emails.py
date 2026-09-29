import re

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import translation
from django_letter.exceptions import InactiveUserError, MissingEmailError

from accounts.models import Organization
from domains.models import Domain
from services.email.msa import emails

MESSAGE_PK = "0195e0f2-8f6a-7c3d-9b1e-2f4a6c8e0d1f"


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
        message_pk=MESSAGE_PK,
        **kwargs,
    )


class TestTestEmail:
    def test_get_context_data__carries_the_template_values(self):
        user = User(email="member@acme.example")
        email = make_test_email(user=user)
        assert email.get_context_data() == emails.get_submission_context() | {
            "user": user,
            "domain": "acme.example",
            "username": "acme",
            "message_pk": MESSAGE_PK,
        }

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

    def test_message__attaches_the_bodies_and_the_wordmark(self):
        message = make_test_email().message()
        assert [part.get_content_type() for part in message.walk()] == [
            "multipart/mixed",
            "multipart/alternative",
            "text/plain",
            "text/html",
            "image/svg+xml",
        ]
        artwork = message.get_payload()[1]
        assert artwork["Content-ID"] == "<word-brand.svg>"
        assert artwork.get_content_disposition() == "inline"
        html = message.get_body(preferencelist=("html",)).get_content()
        assert 'src="cid:word-brand.svg"' in html

    def test_message__plain_text_derives_from_html(self, base_url):
        message = make_test_email().message()
        html = message.get_body(preferencelist=("html",)).get_content()
        text = message.get_body(preferencelist=("plain",)).get_content()
        for part in (html, text):
            assert "acme.example" in part
            assert "delivery log" in part
        link = f"{base_url}/org/acme/email/messages/{MESSAGE_PK}"
        assert f'href="{link}"' in html
        assert f"<{link}>" in text

    def test_message__carries_the_submission_settings(self, base_url):
        submission = emails.get_submission_context()
        html = (
            make_test_email().message().get_body(preferencelist=("html",)).get_content()
        )
        assert submission["smtp_hostname"] in html
        for port in (
            *submission["smtp_implicit_tls_ports"],
            *submission["smtp_starttls_ports"],
        ):
            assert f">{port}<" in html
        assert ">acme<" in html
        assert f'href="{base_url}/org/acme/email/credentials/"' in html
        assert f'href="{base_url}/org/acme/email/domains/"' in html

    def test_message__carries_the_legal_footer(self, base_url):
        html = (
            make_test_email().message().get_body(preferencelist=("html",)).get_content()
        )
        assert "Lennéstr. 19" in html
        for page in ("imprint", "privacy"):
            assert f'href="{base_url}/legal/{page}/"' in html

    def test_render_preview__renders_without_arguments(self, base_url):
        email = emails.TestEmail.render_preview()
        assert email.subject == "Test email from acme.example"
        assert f'<html lang="{settings.LANGUAGE_CODE}">' in email.html
        assert "acme.example" in email.body
        assert f"{base_url}/org/acme/email/messages/" in email.body
        assert re.search(
            rf'<img src="{base_url}/static/img/word-brand\.[0-9a-f]+\.svg"', email.html
        )

    def test_render_preview__uses_given_domain(self):
        email = emails.TestEmail.render_preview(
            domain=Domain(name="custom.example", org=Organization(slug="custom")),
        )
        assert email.subject == "Test email from custom.example"
        assert "This test message left custom.example." in email.body
        assert (
            f"{email.get_base_url().rstrip('/')}/org/custom/email/domains/"
            in email.body
        )

    def test_render_preview__language_argument_wins(self):
        email = emails.TestEmail.render_preview(language="de")
        assert email.language == "de"
        assert '<html lang="de">' in email.html
