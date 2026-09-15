import pytest
from django.contrib.auth.models import User
from django.core import mail

from accounts.models import Membership
from kms import envelope
from kms.models import OrgEncryptionKey, RecoveryEvent
from kms.tasks import notify_recovery_triggered


def make_recovery_event(org, user):
    org_key = OrgEncryptionKey.objects.create(
        org=org,
        public_key=envelope.encode_key(envelope.generate_x25519_keypair().public_key),
        recovery_sealed_org_private_key="recovery-sealed-key",
    )
    return RecoveryEvent.objects.create(
        org_encryption_key=org_key,
        triggered_by=user,
    )


@pytest.mark.django_db(transaction=True)
class TestNotifyRecoveryTriggered:
    def test_notify_recovery_triggered__emails_all_members(self, org, user, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        event = make_recovery_event(org, user)
        notify_recovery_triggered.enqueue(recovery_event_id=event.pk)
        recipients = [email.to[0] for email in mail.outbox]
        assert user.email in recipients
        assert other_user.email in recipients
        assert len(mail.outbox) == 2

    def test_notify_recovery_triggered__skips_members_without_email(self, org, user):
        no_email_user = User.objects.create_user(
            username="carol",
            email="",
            password="secret",
        )
        Membership.objects.create(
            org=org, user=no_email_user, role=Membership.Role.WRITE
        )
        event = make_recovery_event(org, user)
        notify_recovery_triggered.enqueue(recovery_event_id=event.pk)
        recipients = [email.to[0] for email in mail.outbox]
        assert user.email in recipients
        assert len(mail.outbox) == 1
