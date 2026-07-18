# Coding Conventions

This document records coding conventions for the Relay project.
Update it based on review feedback.

## URLs

- Use nested `include()` for cascaded paths:

  ```python
  path("credentials/", include([
      path("new", …),
  ]))
  ```

- CRUD actions on objects should **not** end with a trailing slash.
  List/create views may use a trailing slash.

## Primary Keys

- Prefer `BigAutoField` (bigint) for most models — easier to work with in Django.
- Use slugs based on title for URL patterns, not UUIDs.
- Exception: `Message` and `Transmission` use UUIDv7 as PK because IDs are
  used as SMTP message-ids and need to be unique/transferable outside Postgres.
- Use `db_default` with a PostgreSQL database function (e.g. `UuidV7()`) for
  database-side UUIDv7 generation, alongside the Python `default=uuid.uuid7`
  for ORM-level defaults.
- Objects with a FK to `Message` (e.g. `Transmission`) should use UUIDv7 PK too.

## Model Fields

- All fields should have `verbose_name` and `help_text` (except FK and PK).
- Use `db_defaults` where a database-side default is appropriate.

## Model.save()

- Always include explicit `update_fields=` to avoid race conditions and be explicit.
- Use `force_insert=True` when creating a new instance.

## Functions

- No private functions (underscore prefix) — this project is not for redistribution.
- Function names should be descriptive, not ambiguous.

## Control Flow

- Prefer `match`/`case` statements over if-chains where applicable.

## Imports

- Import views as `from . import views` in URL configs.
- Move imports to the top of the file, not inside functions.
- Do not import with different names (no `import x as y`) unless necessary.
- Do not import per-property — import the module directly.

## Authentication

- Use `social-auth-app-django` (python-social-auth) for OAuth providers
  instead of custom OAuth code.
- Custom pipeline steps live in `accounts/pipelines.py`.

## Naming

- Use names that cover both ingress and egress when a model tracks
  bidirectional events (e.g. `Transmission`, not `Delivery`).
