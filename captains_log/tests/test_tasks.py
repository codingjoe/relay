from datetime import timedelta
from unittest.mock import patch

import pytest
from crontask import scheduler
from django.utils import timezone
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership
from captains_log import tasks
from captains_log.content import CaptainsLogContent
from captains_log.emails import station_log_notification

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


class TestSendStationLogAnnouncements:
    def test_announcements__queues_yesterday_log(self, monkeypatch):
        yesterday = timezone.localdate() - timedelta(days=1)
        monkeypatch.setattr(
            CaptainsLogContent,
            "get_articles",
            classmethod(lambda cls: iter([(SLUG, {"date": yesterday})])),
        )

        with patch("captains_log.tasks.send_station_log") as task:
            tasks.send_station_log_announcements.func()

        task.enqueue.assert_called_once_with(slug=SLUG)

    def test_announcements__skips_older_logs(self, monkeypatch):
        older = timezone.localdate() - timedelta(days=2)
        monkeypatch.setattr(
            CaptainsLogContent,
            "get_articles",
            classmethod(lambda cls: iter([(SLUG, {"date": older})])),
        )

        with patch("captains_log.tasks.send_station_log") as task:
            tasks.send_station_log_announcements.func()

        task.enqueue.assert_not_called()


class TestSendStationLogSchedule:
    def test_announcements__runs_each_morning(self):
        job = next(
            job
            for job in scheduler.get_jobs()
            if job.name == tasks.send_station_log_announcements.name
        )
        fields = {field.name: str(field) for field in job.trigger.fields}

        assert fields["hour"] == "9"
        assert fields["minute"] == "0"
