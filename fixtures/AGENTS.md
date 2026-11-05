# Fixture Instructions

Load with `manage.py loaddata fixtures/initial_data.yaml`.

Refresh:

1. Wipe and migrate: `rm -f db.sqlite3 && uv run python manage.py migrate`.
2. Update the YAML and binary message files. `auth.permission` rows come from
   `post_migrate`. The two `kms.signingkey` rows use Fernet keys from the
   local KMS key, so they are not portable across environments.
3. Validate the YAML with the `yamlfmt` hook.
