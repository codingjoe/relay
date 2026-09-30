from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership
from domains.models import Domain
from services.email.msa.models import OutgoingMessage, SuppressionEntry
from services.email.reputation import chart
from services.email.reputation.digest import (
    build_digest_context,
    build_org_digest,
    count_window_recipients,
    digest_illustration,
    iter_digest_members,
    message_interval,
)
from services.email.reputation.tests.conftest import make_stats


def make_message(
    org,
    rcpt_to="rcpt@example.com",
    *,
    status=OutgoingMessage.Status.SENT,
    days_ago=0,
):
    domain = Domain.objects.get_or_create(name="acme.com", org=org)[0]
    message = OutgoingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="sender@acme.com",
        rcpt_to=rcpt_to,
        status=status,
        raw_body=SimpleUploadedFile("message.eml", b"body"),
    )
    if days_ago:
        OutgoingMessage.objects.filter(pk=message.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return message


class TestMessageInterval:
    def test_message_interval__says_nothing_without_messages(self):
        assert message_interval(0) == ""

    def test_message_interval__counts_the_hours_between_messages(self):
        assert message_interval(1) == "one every 24 hours"

    def test_message_interval__counts_the_minutes_between_messages(self):
        assert message_interval(100) == "one every 14 minutes"

    def test_message_interval__counts_the_seconds_between_messages(self):
        assert message_interval(1000) == "one every 86 seconds"

    def test_message_interval__leaves_a_single_second_in_the_singular(self):
        assert message_interval(50000) == "one every second"

    def test_message_interval__keeps_a_full_second_in_the_singular(self):
        assert message_interval(86_400) == "one every second"

    def test_message_interval__caps_at_more_than_one_a_second(self):
        assert message_interval(86_401) == "more than one a second"


@pytest.mark.django_db
class TestCountWindowRecipients:
    def test_count_window_recipients__counts_distinct_addresses_in_the_window(
        self, org
    ):
        make_message(org, "one@example.com")
        make_message(org, "one@example.com")
        make_message(org, "two@example.com")
        make_message(org, "three@example.com", days_ago=40)

        assert count_window_recipients(org, 7) == 2

    def test_count_window_recipients__leaves_out_sandboxed_messages(self, org):
        make_message(
            org, "sandbox@example.com", status=OutgoingMessage.Status.SANDBOXED
        )

        assert count_window_recipients(org, 7) == 0

    def test_count_window_recipients__counts_a_failed_delivery(self, org):
        make_message(org, "failed@example.com", status=OutgoingMessage.Status.FAILED)

        assert count_window_recipients(org, 7) == 1


class TestDigestIllustration:
    def test_digest_illustration__points_at_the_pair_for_a_clean_window(self):
        assert digest_illustration(make_stats()) == (
            "img/illustrations/all-the-data-light.svg",
            "img/illustrations/all-the-data-dark.svg",
        )

    def test_digest_illustration__drops_the_pair_over_a_limit(self):
        assert digest_illustration(make_stats(hard_bounce_over_limit=True)) == ("", "")


@pytest.mark.django_db
class TestBuildDigestContext:
    def test_build_digest_context__carries_the_numbers_and_the_limits(
        self, org, settings
    ):
        settings.RELAY_REPUTATION_WINDOW_DAYS = 7
        settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD = 0.05
        settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD = 0.001
        settings.RELAY_FREE_MONTHLY_MESSAGES = 1000
        stats = make_stats(total_sent=70)

        context = build_digest_context(
            org,
            stats=stats,
            month_messages=42100,
            daily_counts=[10] * 7,
            recipients=214,
        )

        assert context["stats"] == stats
        assert context["organization"] == "test-org"
        assert context["window_phrase"] == "last 7 days"
        assert context["daily_average"] == 10
        assert context["message_interval"] == "one every 2 hours"
        assert context["month_messages"] == 42100
        assert context["recipients"] == 214
        assert context["bounce_threshold"] == 0.05
        assert context["complaint_threshold"] == 0.001
        assert context["free_monthly_messages"] == 1000
        assert context["cost"] == Decimal("28.36")
        assert "<svg" not in context["week_chart"]
        assert f'bgcolor="{chart.COLUMN}"' in context["week_chart"]
        assert context["illustration_dark"] == "img/illustrations/all-the-data-dark.svg"
        assert context["dashboard_path"] == reverse(
            "monitoring:overview", kwargs={"org_slug": "test-org"}
        )

    def test_build_digest_context__leaves_the_chart_out_of_a_quiet_window(self, org):
        context = build_digest_context(
            org,
            stats=make_stats(),
            month_messages=0,
            daily_counts=[0] * 7,
            recipients=0,
        )

        assert context["week_chart"] == ""
        assert context["message_interval"] == ""
        assert context["cost"] == Decimal("0.00")


@pytest.mark.django_db
class TestBuildOrgDigest:
    def test_build_org_digest__counts_the_window(self, org, settings):
        settings.RELAY_REPUTATION_WINDOW_DAYS = 2
        make_message(org, "one@example.com")
        make_message(org, "one@example.com")
        make_message(org, "two@example.com", status=OutgoingMessage.Status.SANDBOXED)
        make_message(org, "three@example.com", days_ago=40)

        digest = build_org_digest(org)

        assert digest["stats"]["total_sent"] == 2
        assert digest["daily_average"] == 1
        assert digest["message_interval"] == "one every 24 hours"
        assert digest["recipients"] == 1
        assert digest["month_messages"] == 2
        assert digest["window_phrase"] == "last 2 days"
        assert digest["cost"] == Decimal("0.00")
        assert f'bgcolor="{chart.COLUMN}"' in digest["week_chart"]
        assert digest["dashboard_path"] == reverse(
            "monitoring:overview", kwargs={"org_slug": "test-org"}
        )

    def test_build_org_digest__counts_a_zero_window_as_one_day(self, org, settings):
        settings.RELAY_REPUTATION_WINDOW_DAYS = 0
        make_message(org, "one@example.com")

        digest = build_org_digest(org)

        assert digest["window_phrase"] == "last 1 day"
        assert f'bgcolor="{chart.COLUMN}"' in digest["week_chart"]


@pytest.mark.django_db
class TestIterDigestMembers:
    def test_iter_digest_members__yields_every_reachable_member(
        self, org, user, other_user
    ):
        Membership.objects.create(org=org, user=other_user)

        assert [membership.user.email for membership in iter_digest_members(org)] == [
            "alice@example.com",
            "bob@example.com",
        ]

    def test_iter_digest_members__skips_a_suppressed_address(
        self, org, user, other_user
    ):
        Membership.objects.create(org=org, user=other_user)
        SuppressionEntry.objects.create_or_update(org=org, email=user.email)

        assert [membership.user.email for membership in iter_digest_members(org)] == [
            "bob@example.com"
        ]

    def test_iter_digest_members__skips_members_without_a_usable_address(
        self, org, other_user
    ):
        other_user.is_active = False
        other_user.save(update_fields=["is_active"])
        Membership.objects.create(org=org, user=other_user)
        Membership.objects.create(
            org=org, user=User.objects.create_user(username="carol", email="")
        )

        assert [membership.user.email for membership in iter_digest_members(org)] == [
            "alice@example.com"
        ]
