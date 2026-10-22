from django.db import migrations
from django.utils import timezone


def start_campaigns(apps, schema_editor):
    """Start a sequence for every organization that has not finished onboarding."""
    Organization = apps.get_model("accounts", "Organization")
    OutgoingMessage = apps.get_model("msa", "OutgoingMessage")
    MsaCredential = apps.get_model("msa", "MsaCredential")
    OnboardingCampaign = apps.get_model("dashboard", "OnboardingCampaign")
    now = timezone.now()
    for org in Organization.objects.iterator():
        has_outgoing_message = OutgoingMessage.objects.filter(org_id=org.pk).exists()
        connected = MsaCredential.objects.filter(
            org_id=org.pk,
            last_used_at__isnull=False,
        ).exists()
        if not (has_outgoing_message and connected):
            OnboardingCampaign.objects.get_or_create(
                org_id=org.pk,
                defaults={"next_send_at": now},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_onboarding_campaign"),
        ("msa", "0006_remove_outgoingmessage_feedback_id"),
    ]

    operations = [
        migrations.RunPython(start_campaigns, migrations.RunPython.noop),
    ]
