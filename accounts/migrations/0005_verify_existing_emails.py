from django.db import migrations
from django.utils import timezone


def verify_existing_emails(apps, schema_editor):
    """Treat existing users' email addresses as already verified.

    Legacy emails were confirmed by the removed GitHub OAuth provider or
    set by the operator, so security mail to them must keep flowing after
    this migration. New signups verify through their own link.
    """
    EmailVerification = apps.get_model("accounts", "EmailVerification")
    User = apps.get_model("auth", "User")
    now = timezone.now()
    for user in User.objects.exclude(email=""):
        EmailVerification.objects.get_or_create(
            user=user,
            defaults={"email": user.email, "verified_at": now},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_emailverification"),
    ]

    operations = [
        migrations.RunPython(verify_existing_emails, migrations.RunPython.noop),
    ]
