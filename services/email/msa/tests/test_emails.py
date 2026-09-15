from django.conf import settings

from accounts.models import Organization
from domains.models import Domain
from services.email.msa import emails


def make_test_email(*, domain=None, **kwargs):
    return emails.TestEmail(
        domain=domain or Domain(name="acme.example", org=Organization(slug="acme")),
        recipient="member@acme.example",
        to=["member@acme.example"],
        **kwargs,
    )


class TestTestEmail:
    def test_get_context_data__builds_sender_and_dashboard_url(self):
        email = make_test_email()
        assert email.get_context_data() == {
            "domain": "acme.example",
            "sender": f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example",
            "recipient": "member@acme.example",
            "dashboard_url": (
                f"{settings.RELAY_PLATFORM_BASE_URL}/org/acme/email/messages/"
            ),
        }

    def test_init__defaults_language_and_base_url(self):
        email = make_test_email()
        assert email.language == settings.LANGUAGE_CODE
        assert email.base_url == settings.RELAY_PLATFORM_BASE_URL

    def test_init__arguments_win(self):
        email = make_test_email(language="de", base_url="https://mail.example.org")
        assert email.language == "de"
        assert email.base_url == "https://mail.example.org"

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

    def test_message__plain_text_derives_from_html(self):
        message = make_test_email().message()
        html = message.get_body(preferencelist=("html",)).get_content()
        text = message.get_body(preferencelist=("plain",)).get_content()
        assert f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example" in html
        assert f"{settings.RELAY_POSTMASTER_LOCAL_PART}@acme.example" in text
        assert "member@acme.example" in text
        link = f"{settings.RELAY_PLATFORM_BASE_URL}/org/acme/email/messages/"
        assert f'href="{link}"' in html
        assert f"<{link}>" in text

    def test_render_preview__renders_without_arguments(self):
        email = emails.TestEmail.render_preview()
        assert email.subject == "Test email from acme.example"
        assert email.recipient == "member@acme.example"
        assert f'<html lang="{settings.LANGUAGE_CODE}">' in email.html
        assert (
            f"{settings.RELAY_PLATFORM_BASE_URL}/org/acme/email/messages/" in email.body
        )

    def test_render_preview__uses_given_domain(self):
        email = emails.TestEmail.render_preview(
            domain=Domain(name="custom.example", org=Organization(slug="custom")),
            recipient="member@custom.example",
        )
        assert email.subject == "Test email from custom.example"
        assert "member@custom.example" in email.html

    def test_render_preview__language_argument_wins(self):
        email = emails.TestEmail.render_preview(language="de")
        assert email.language == "de"
        assert '<html lang="de">' in email.html
