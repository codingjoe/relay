from django.db import migrations

LEGACY_TABLES = (
    "social_auth_association",
    "social_auth_code",
    "social_auth_nonce",
    "social_auth_partial",
    "social_auth_usersocialauth",
)


def move_github_social_accounts(apps, schema_editor):
    """Carry every GitHub link to allauth, then drop the social-auth tables."""
    connection = schema_editor.connection
    if "social_auth_usersocialauth" in connection.introspection.table_names():
        social_account = apps.get_model("socialaccount", "SocialAccount")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, uid FROM social_auth_usersocialauth"
                " WHERE provider = 'github'"
            )
            rows = cursor.fetchall()
            # allauth refetches the profile on the next sign-in, so the link is
            # all that carries over.
            social_account.objects.bulk_create(
                [
                    social_account(user_id=user_id, provider="github", uid=uid)
                    for user_id, uid in rows
                ],
                ignore_conflicts=True,
            )
            for table in LEGACY_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
            cursor.execute("DELETE FROM django_migrations WHERE app = 'social_django'")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_organization_billing_is_active"),
        ("socialaccount", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_github_social_accounts, migrations.RunPython.noop),
    ]
