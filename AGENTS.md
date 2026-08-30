# Agent Instructions

## Project overview

relay is a B2B SaaS communication platform (email, VoIP, and more) on
Django 6.0 / Python 3.14. Its differentiator is simplicity: relay handles
the DNS and email plumbing, so sending and receiving work with near-zero
configuration. A built-in authoritative nameserver delivers this: users
only set NS delegation and DMARC, and relay serves MX, SPF, DKIM,
Return-Path, MTA-STS, and TLS-RPT automatically. GitHub OAuth handles
authentication.

## Architecture & tech stack

Three services from one codebase, each a separate Docker container:

- **Web**: Django web UI + admin (Granian ASGI in production, `runserver` in development).
- **DNS**: Authoritative nameserver (dnslib, UDP+TCP). `domains/resolver.py`
  builds DNS records from `Domain` model properties. No zone files.
- **MSA**: Outgoing mail submissions (aiosmtpd). `msa/handlers.py`
  authenticates via `MsaCredential`, stores the raw body as a `FileField`,
  and dispatches delivery via the Django task framework. Incoming (MTA)
  mail is handled by the `mta` app.

Apps: `root` (settings, root URLs, base templates. No cross-app model
imports), `accounts` (Organization, Membership, abstract Credential, OAuth,
org CRUD), `domains` (Domain, DNS resolver/server/services, domain
views), `kms` (SigningKey, Fernet ciphertext, public/private keypair
generation, signing. No app-specific knowledge), `msa` (OutgoingMessage, Transmission, MsaCredential, delivery
task, handler/server, message + credential views), `mta` (IncomingMessage, Webhook,
WebhookDelivery, TlsReport, TlsFailure, MX server, webhook dispatch, MTA-STS),
`services.email.dashboard` (the unified
transactional-email dashboard), `legal` (Markdown legal pages), `abstract`
(shared TimeStamped model, admin mixins, Markdown utils).

App dependencies flow in one direction. See the graph in `README.md`:
`dashboard → msa, mta, dmarc, message`, `msa, mta, dmarc → message, domains, accounts, kms`, `message → domains, accounts`, `domains → accounts, kms`, `accounts → kms`. Apps
must not import from their dependents.

Key tech: Django 6.0 task framework, PostgreSQL 18+ (uses `uuidv7()`), Redis,
S3 via django-storages, social-auth-app-django, basecoat CSS (via PostCSS
with wireit).

## Core commands & workflows

- `uv sync`. Install dependencies. **Use `uv` only**, never `pip`.
- `pnpm install`. Install Node.js dependencies (Tailwind, basecoat, PostCSS, wireit).
- `pnpm run build`. Compile CSS via PostCSS (`src/css/app.css` → `root/static/css/app.css`).
- `pnpm run dev`. Watch and recompile CSS on change.
- `uv run python manage.py check`: Django system checks.
- `uv run python manage.py makemigrations`. Generate migrations.
- `uv run python manage.py migrate`. Apply migrations.
- `uv run python manage.py runserver`. Dev web server.
- `uv run python manage.py dns`. Start DNS server.
- `uv run python manage.py msa`. Start MSA (SMTP submission) server.
- `uv run python manage.py mta`. Start MTA (MX receiving) server.
- `uv run pre-commit run --all-files`. Lint/format (ruff, djangofmt, pyupgrade,
  mdformat, dockerfmt).
- `uv run ruff check --fix . && uv run ruff format .`. Ruff only.
- `docker compose up -d`. All services via Docker Compose.

## Rules, constraints & safety

- **Never read or expose `.env`, `.env.production`, or secrets.** These files
  contain real OAuth secrets, DB passwords, and Redis passwords.
- **Use `uv` exclusively** for dependency management. Never `pip install`.
- **PostgreSQL 18+ required**: `db_default` uses the `uuidv7()` function.
- **Do not write tests**. The test suite is planned but not yet started.
  Linting/formatting via pre-commit is the current quality gate.
- **Update `CONVENTIONS.md`** when a reviewer identifies a new convention or
  corrects a pattern. This file is the authoritative coding-conventions source.
- **Update `docs/docs/`** when a change alters documented behavior (sending,
  receiving, DNS, webhooks, message statuses, hosting, security, privacy).
  The user-facing docs describe how relay works and must not fall behind the code.
- **Extend `.relint.yml`** when a convention can be enforced by regex. Move
  enforced rules out of `CONVENTIONS.md`: `CONVENTIONS.md` documents for
  humans, `.relint.yml` enforces for machines.
- **`root/views.py` must not import models from other first-party apps.**
  Cross-app views belong in their corresponding app.
- **`Model.save()` must include `update_fields=`** to avoid race conditions.
- **No private functions** (underscore prefix). This project is not for
  redistribution.
- **Follow `CONVENTIONS.md`** for all coding patterns (URLs, PKs, fields,
  control flow, imports, naming).

## Quality, testing & definition of done

Before you finish, always:

- Run `uv run python manage.py check`. Must pass with zero issues.
- Run `uv run pre-commit run --all-files`. Must pass (ruff, djangofmt, and more).
- Run `uv run python manage.py makemigrations --check --dry-run`. Verify no
  missing migrations for model changes.
- Verify that URL reversals work for any changed or added routes.
- Update `CONVENTIONS.md` if a review introduces a new convention.
- Update `docs/docs/` when the change touches documented behavior
  (sending, receiving, DNS, webhooks, statuses, hosting, privacy, reliability).
- Follow the `naming-things` guidelines:
  `curl -sSL https://raw.githubusercontent.com/codingjoe/naming-things/refs/heads/main/README.md | cat`

## Running tests

- `pnpm install && pnpm run build && uv run python manage.py collectstatic --noinput`
  must run in advance; the Django checks and templates tests fail without it.
- `uv run --group test pytest`. The last line is always the outcome summary, e.g.
  `13 passed, 2 warnings in 4.20s`. Grep for `[0-9]+ (passed|failed|error)`
  to assert results. Nothing is measured by default.
- `--maxfail=3` stops after three failures.

## Browser automation

Playwright MCP (`.mcp.json`) runs headless and writes screenshots to
`.playwright-mcp/`. The dev server binds to a random localhost port. Read
it from the `runserver` output, then navigate to `http://localhost:<port>`.

The MCP server loads `.playwright-mcp-config.json` (via `--config`)
for `headless` and `outputDir`; no request headers are required (dev
requests are auto-authenticated as the bundled `test` user).

## Test data

Bundle: one user (`test`, password `test`), one org (`acme`), one
domain (`acme.com`), one SMTP credential, three outgoing messages,
three transmissions, three SigningKeys. Load with
`manage.py loaddata fixtures/initial_data.yaml`. Refresh with:

1. Wipe the database and re-apply migrations:
   `rm -f db.sqlite3 && uv run python manage.py migrate`
1. Update the YAML fixture and any binary message files it references.
   The fixture is plain YAML. Edit it directly. `auth.permission`
   rows are auto-generated by `post_migrate` and are not part of the
   fixture. `kms.signingkey` rows are created by the data migration
   `message.0002_signing_keys`, which generates Fernet-encrypted
   material using the local KMS key (hand-written fixture data cannot
   be portable across Fernet keys. See
   [How to provide initial data for models](https://docs.djangoproject.com/en/6.0/howto/initial-data/)).
1. Validate that the YAML is well-formed via the `yamlfmt`
   pre-commit hook.

The `test` user has no admin or staff access. Only a `write`
membership in `acme`. The dev server authenticates via the
`RemoteUserBackend` middleware when `DEBUG=True`, so the bundle
developer still has the same UX without needing a superuser.

## Pointers to further documentation

- `CONVENTIONS.md`. Authoritative coding conventions (URLs, PKs, model fields,
  save patterns, control flow, imports, authentication, naming).
- `README.md`. Setup guide, architecture overview, app dependency graph,
  free sender domain docs.
- `REVIEW.md`. The reviewer's standing rules (conventions, dependency
  direction). `CLAUDE.md` and `.github/copilot-instructions.md` symlink to it.
- `root/settings.py`. All `RELAY_*` config and environment variables.
- `docs/docs/`. User-facing product documentation, served at `/docs/`.
- `legal/docs/`. Legal page Markdown sources (imprint, privacy, terms).

## Examples

**Good:** Add a field to `OutgoingMessage` with `verbose_name` and `help_text`.
Then do the following steps:

1. Generate a migration.
1. Run `manage.py check` and `makemigrations --check`.
1. Verify that `CONVENTIONS.md` does not need an update.

**Bad:** Import a model from `domains` in `root/views.py`, use `pip install`
for a dependency, or save a model without `update_fields=`.
