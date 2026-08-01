"""Seed the local database with the test fixture bundle.

Used to regenerate ``fixtures/initial_data.json``. See ``AGENTS.md``
for the full workflow.
"""

from email.message import EmailMessage

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from accounts.models import Membership, Organization
from domains.models import Domain
from kms.models import SigningKey
from smtp.models import OutgoingMessage, SmtpCredential, Transmission
from tx_mail.models import Message

User = get_user_model()


class Command(BaseCommand):
    """Populate the database with the AGENTS.md test bundle."""

    help = "Seed one user, one org, one domain, one SMTP credential, three outgoing messages, and three transmissions."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="test",
            defaults={
                "email": "test@example.com",
                "is_superuser": True,
                "is_staff": True,
            },
        )
        if created:
            user.set_password("test")
            user.save(update_fields=["password"])
        self.stdout.write(f"User: {user.pk}")

        org, _ = Organization.objects.get_or_create(slug="acme")
        Membership.objects.get_or_create(
            user=user,
            org=org,
            defaults={"role": Membership.Role.ADMIN},
        )
        self.stdout.write(f"Org: {org.slug}")

        keys = list(
            SigningKey.objects.filter(
                algorithm__in=["rsa-2048", "rsa-1024", "ed25519"]
            ).order_by("algorithm")
        )
        if len(keys) < 3:
            for algorithm in ["rsa-2048", "rsa-1024", "ed25519"]:
                if not SigningKey.objects.filter(algorithm=algorithm).exists():
                    keys.append(SigningKey.generate(algorithm))
            keys = list(
                SigningKey.objects.filter(
                    algorithm__in=["rsa-2048", "rsa-1024", "ed25519"]
                ).order_by("algorithm")
            )
        for sk in keys:
            self.stdout.write(f"SigningKey: {sk.pk} {sk.algorithm}")

        domain, _ = Domain.objects.get_or_create(
            name="acme.com",
            defaults={
                "org": org,
                "nameserver_status": Domain.Status.OK,
                "spf_status": Domain.Status.OK,
                "dkim_status": Domain.Status.OK,
                "dmarc_status": Domain.Status.OK,
                "verified_at": "2026-01-01T00:00:00Z",
                "dkim_key_rsa2048": keys[0],
                "dkim_key_rsa1024": keys[1],
                "dkim_key_ed25519": keys[2],
            },
        )
        self.stdout.write(f"Domain: {domain.name}")

        smtp_cred, raw_key = SmtpCredential.objects.create_with_key(
            org=org,
            name="Default",
            type=SmtpCredential.Type.SMTP,
        )
        self.stdout.write(f"SmtpCredential: {smtp_cred.pk} raw_key={raw_key[:8]}…")

        for n in range(1, 4):
            raw = EmailMessage()
            raw["From"] = f"sender{n}@acme.com"
            raw["To"] = f"recipient{n}@example.com"
            raw["Subject"] = f"Test message {n}"
            raw["Message-ID"] = f"<test{n}@acme.com>"
            raw.set_content(f"Hello recipient {n}!\n")
            msg = OutgoingMessage(
                org=org,
                kind=Message.Kind.OUTGOING,
                mail_from=f"sender{n}@acme.com",
                rcpt_to=f"recipient{n}@example.com",
                subject=f"Test message {n}",
                message_id=f"<test{n}@acme.com>",
                sender=user,
                domain=domain,
                credential=smtp_cred,
                status="sent",
            )
            msg.raw_body.save(f"{msg.id}.eml", ContentFile(raw.as_bytes()), save=False)
            msg.save()
            self.stdout.write(f"OutgoingMessage {n}: {msg.pk}")
            Transmission.objects.create(
                message=msg,
                status="sent",
                code=250,
                output="OK",
                details=f"Test transmission {n}",
                sent_with_ssl=True,
            )
            self.stdout.write(f"  Transmission {n}: ok")

        self.stdout.write("---DONE---")
        self.stdout.write(
            f"Totals: User={User.objects.count()} "
            f"Org={Organization.objects.count()} "
            f"Domain={Domain.objects.count()} "
            f"SmtpCred={SmtpCredential.objects.count()} "
            f"OutgoingMsg={OutgoingMessage.objects.count()} "
            f"Transmission={Transmission.objects.count()} "
            f"Message={Message.objects.count()} "
            f"SigningKey={SigningKey.objects.count()}"
        )
