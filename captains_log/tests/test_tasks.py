from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership
from captains_log import tasks
from captains_log.emails import station_log_notification
from services.email.msa.models import SuppressionEntry

SLUG = "2026-10"


def disable_notification(email):
    field = NotificationPreference._meta.get_field("email_hash")
    NotificationPreference.objects.set_enabled_hash(
        station_log_notification,
        field.hash_email(email),
        False,
    )


@pytest.mark.django_db
class TestSendStationLog:
    def test_send_station_log__mails_each_member_once(self, user, org, mailoutbox):
        tasks.send_station_log.func(slug=SLUG)

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]
        assert mailoutbox[0].subject == "A new station log: October 2026"

    def test_send_station_log__mails_a_member_of_two_orgs_once(
        self, user, org, write_org, mailoutbox
    ):
        Membership.objects.create(org=write_org, user=user)

        tasks.send_station_log.func(slug=SLUG)

        assert sorted(message.to[0] for message in mailoutbox) == [
            "alice@example.com",
            "bob@example.com",
        ]

    def test_send_station_log__skips_a_member_who_opted_out(
        self, user, org, mailoutbox
    ):
        disable_notification(user.email)

        tasks.send_station_log.func(slug=SLUG)

        assert mailoutbox == []

    def test_send_station_log__skips_a_suspended_organization(
        self, user, org, mailoutbox
    ):
        org.suspended_at = timezone.now()
        org.save(update_fields=["suspended_at"])

        tasks.send_station_log.func(slug=SLUG)

        assert mailoutbox == []

    def test_send_station_log__skips_a_suppressed_address(self, user, org, mailoutbox):
        SuppressionEntry.objects.create_or_update(
            org=org,
            email=user.email,
            reason=SuppressionEntry.Reason.MANUAL,
        )

        tasks.send_station_log.func(slug=SLUG)

        assert mailoutbox == []


class TestSendStationLogCommand:
    @pytest.mark.django_db
    def test_dry_run__reports_without_sending(self, user, org, mailoutbox, capsys):
        call_command("send_station_log", SLUG, "--dry-run")

        assert mailoutbox == []
        assert "2026-10 would reach 1 member." in capsys.readouterr().out

    @pytest.mark.django_db
    def test_command__queues_the_task(self, user, org):
        with patch(
            "captains_log.management.commands.send_station_log.send_station_log"
        ) as task:
            call_command("send_station_log", SLUG)

        task.enqueue.assert_called_once_with(slug=SLUG)

    @pytest.mark.django_db
    def test_command__sends_now(self, user, org, mailoutbox):
        call_command("send_station_log", SLUG, "--now")

        assert [message.to[0] for message in mailoutbox] == ["alice@example.com"]

    def test_command__rejects_an_unknown_log(self):
        with pytest.raises(CommandError):
            call_command("send_station_log", "1999-01")
