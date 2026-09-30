import pytest

from accounts.models import Organization
from services.email.reputation import chart, emails
from services.email.reputation.digest import build_digest_context
from services.email.reputation.tests.conftest import make_stats

NBSP = "\N{NO-BREAK SPACE}"
SAMPLE_DAYS = [980, 1420, 2310, 1750, 2640, 1880, 1500]


def make_digest(stats=None, *, month_messages=42100, daily_counts=None, recipients=214):
    return build_digest_context(
        Organization(slug="acme"),
        stats=stats or make_stats(total_sent=12480, soft_bounces=17),
        month_messages=month_messages,
        daily_counts=SAMPLE_DAYS if daily_counts is None else daily_counts,
        recipients=recipients,
    )


def card_containing(html, label):
    """Return the markup of the digest card whose label matches."""
    position = html.index(f">{label}<")
    return html[html.rindex("<td", 0, position) : html.index("</td>", position)]


def render(digest):
    email = emails.WeeklyDigestEmail(digest=digest, language="en-us")
    email.render()
    return email


@pytest.fixture
def email():
    return emails.WeeklyDigestEmail(digest=make_digest(), language="en-us")


class TestWeeklyDigestEmail:
    def test_get_headline__names_the_fix_over_a_limit(self, email):
        assert (
            email.get_headline(make_stats(hard_bounce_over_limit=True), "acme")
            == "Something to fix at acme."
        )

    def test_get_headline__notes_a_week_without_messages(self, email):
        assert email.get_headline(make_stats(), "acme") == "acme took the week off."

    def test_get_headline__reports_a_clean_week(self, email):
        assert (
            email.get_headline(make_stats(total_sent=40), "acme")
            == "A clean week at acme."
        )

    def test_get_headline__reports_a_week_with_bumps(self, email):
        assert (
            email.get_headline(make_stats(total_sent=40, hard_bounces=1), "acme")
            == "A week with a few bumps at acme."
        )

    def test_get_verdict__reports_both_limits(self, email):
        assert email.get_verdict(
            make_stats(hard_bounce_over_limit=True, complaint_over_limit=True)
        ) == (
            "The hard bounce rate and the complaint rate are both over "
            "their limits. The numbers are below."
        )

    def test_get_verdict__reports_the_bounce_limit(self, email):
        assert email.get_verdict(make_stats(hard_bounce_over_limit=True)) == (
            "The hard bounce rate is over its limit. The numbers are below."
        )

    def test_get_verdict__reports_the_complaint_limit(self, email):
        assert email.get_verdict(make_stats(complaint_over_limit=True)) == (
            "The complaint rate is over its limit. The numbers are below."
        )

    def test_get_verdict__reports_a_week_without_messages(self, email):
        assert email.get_verdict(make_stats()) == (
            "Nothing left the building. A spotless record, "
            "achieved by doing nothing at all."
        )

    def test_get_verdict__reports_a_clean_week(self, email):
        assert email.get_verdict(make_stats(total_sent=40)) == (
            "Not one hard bounce. Receivers file your mail under inbox, "
            "where the humans are."
        )

    def test_get_verdict__reports_a_week_with_bumps(self, email):
        assert email.get_verdict(make_stats(total_sent=40, hard_bounces=1)) == (
            "A few bounces or complaints, comfortably inside the limits. "
            "Boring is the goal, and this is boring."
        )

    def test_get_subject__names_the_organization_and_the_count(self, email):
        assert (
            email.get_subject(**email.get_context_data())
            == "acme sent 12,480 messages out the door"
        )

    def test_get_subject__leaves_a_single_message_in_the_singular(self):
        email = emails.WeeklyDigestEmail(
            digest=make_digest(make_stats(total_sent=1)), language="en-us"
        )

        assert (
            email.get_subject(**email.get_context_data())
            == "acme sent one message out the door"
        )

    def test_get_context_data__adds_the_headline_and_the_count(self, email):
        context = email.get_context_data()

        assert context["stats"] == make_stats(total_sent=12480, soft_bounces=17)
        assert context["headline"] == "A clean week at acme."
        assert context["sent"] == "12,480"
        assert context["verdict"].startswith("Not one hard bounce.")

    def test_render__carries_the_numbers_and_the_copy(self):
        email = render(make_digest(make_stats(total_sent=12480, soft_bounces=17)))

        assert email.subject == "acme sent 12,480 messages out the door"
        assert "A clean week at acme." in email.html
        assert "Not one hard bounce." in email.html
        assert "12,480" in email.html
        assert "Messages out the door in the last 7 days." in email.html
        assert "That is about 1,783 messages a day, one every 48 seconds." in email.html
        assert "Those messages were addressed to 214 distinct recipients." in email.html
        assert "42,100 messages this month." in email.html
        assert "bar by bar" in email.html
        assert f'bgcolor="{chart.COLUMN}"' in email.html
        assert "<svg" not in email.html
        assert "all-the-data-light" in email.html
        assert "28.36 EUR" in card_containing(email.html, "Cost")
        assert "1,000 a month on the house." in card_containing(email.html, "Cost")
        assert "0.00" + NBSP + "%" in card_containing(email.html, "Hard bounce rate")
        assert "0.00" + NBSP + "%" in card_containing(email.html, "Complaint rate")
        assert "We allow up to 5.00" + NBSP + "%." in card_containing(
            email.html, "Hard bounce rate"
        )
        assert "We allow up to 0.10" + NBSP + "%." in card_containing(
            email.html, "Complaint rate"
        )
        assert "relay suspends the organization" not in email.html

    def test_render__opens_with_the_rate_that_is_over(self):
        email = render(
            make_digest(
                make_stats(
                    total_sent=1400,
                    hard_bounces=140,
                    hard_bounce_rate=0.1,
                    hard_bounce_over_limit=True,
                ),
                month_messages=2200,
                daily_counts=[200] * 7,
                recipients=200,
            )
        )

        assert "Something to fix at acme." in email.html
        assert (
            "The hard bounce rate is over its limit. The numbers are below."
            in email.html
        )
        assert "relay suspends the organization" in email.html
        assert "That is about 200 messages a day, one every 7 minutes." in email.html
        assert "0.83 EUR" in card_containing(email.html, "Cost")
        assert "10.00" + NBSP + "%" in card_containing(email.html, "Hard bounce rate")
        assert "digest-card-body--bad" in card_containing(
            email.html, "Hard bounce rate"
        )
        assert "digest-card-value--bad" in card_containing(
            email.html, "Hard bounce rate"
        )
        assert "--bad" not in card_containing(email.html, "Cost")
        assert "--bad" not in card_containing(email.html, "Complaint rate")
        assert "all-the-data-light" not in email.html

    def test_render__reads_a_single_message_in_the_singular(self):
        email = render(
            make_digest(
                make_stats(
                    total_sent=7,
                    complaints=1,
                    complaint_rate=0.14,
                    complaint_over_limit=True,
                ),
                month_messages=7,
                daily_counts=[7, 0, 0, 0, 0, 0, 0],
                recipients=1,
            )
        )

        assert "Something to fix at acme." in email.html
        assert (
            "The complaint rate is over its limit. The numbers are below." in email.html
        )
        assert "That is about 1 message a day, one every 24 hours." in email.html
        assert "Those messages were addressed to 1 distinct recipient." in email.html
        assert "7 messages this month." in email.html
        assert "Free" in card_containing(email.html, "Cost")
        assert "14.00" + NBSP + "%" in card_containing(email.html, "Complaint rate")
        assert "digest-card-body--bad" in card_containing(email.html, "Complaint rate")
        assert "--bad" not in card_containing(email.html, "Hard bounce rate")

    def test_render__leaves_out_what_the_week_did_not_do(self):
        email = render(
            make_digest(
                make_stats(),
                month_messages=0,
                daily_counts=[0] * 7,
                recipients=0,
            )
        )

        assert "acme took the week off." in email.html
        assert "Nothing left the building." in email.html
        assert "bar by bar" not in email.html
        assert f'bgcolor="{chart.COLUMN}"' not in email.html
        assert "message a day" not in email.html
        assert "distinct recipient" not in email.html
        assert "all-the-data-light" in email.html
        assert "Free" in card_containing(email.html, "Cost")
        assert "--bad" not in card_containing(email.html, "Cost")
        assert "--bad" not in card_containing(email.html, "Hard bounce rate")
        assert "--bad" not in card_containing(email.html, "Complaint rate")

    def test_render_preview__fills_in_a_busy_window(self):
        email = emails.WeeklyDigestEmail.render_preview(language="en-us")

        assert "12,480" in email.html
        assert "bar by bar" in email.html
