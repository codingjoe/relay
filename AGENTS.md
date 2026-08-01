# Agent Instructions

## Project overview

Relay is a B2B SaaS communication platform (email, VoIP, and more) on
Django 6.0 / Python 3.14. The key feature is a **built-in authoritative
nameserver**. Users only set NS delegation and DMARC. The nameserver
serves MX, SPF, DKIM, and Return-Path automatically. GitHub OAuth
handles authentication.

## Architecture & tech stack

Three services from one codebase, each a separate Docker container:

- **Web** — Django web UI + admin (Granian ASGI in production, `runserver` in development).
- **DNS** — Authoritative nameserver (dnslib, UDP+TCP). `domains/resolver.py`
  builds DNS records from `Domain` model properties — no zone files.
- **SMTP** — Outgoing mail submissions (aiosmtpd). `smtp/handlers.py`
  authenticates via `SmtpCredential`, stores the raw body as a `FileField`,
  and dispatches delivery via the Django task framework. Incoming (MX)
  mail is out of scope for now.

Apps: `root` (settings, root URLs, base templates — no cross-app model
imports), `accounts` (Organization, Membership, abstract Credential, OAuth,
org CRUD), `domains` (Domain, DNS resolver/server/services, domain
views), `kms` (SigningKey, Fernet ciphertext, public/private keypair
generation, signing — no app-specific knowledge), `smtp` (OutgoingMessage, Transmission, SmtpCredential, delivery
task, handler/server, message + credential views), `tx_email` (the unified
transactional-email dashboard), `legal` (Markdown legal pages), `abstract`
(shared TimeStamped model, admin mixins, Markdown utils).

App dependencies flow in one direction — see the graph in `README.md`:
`tx_email → smtp, mx`, `smtp, mx → domains, accounts, kms`, `domains → accounts, kms`, `accounts → kms`. Apps
must not import from their dependents.

Key tech: Django 6.0 task framework, PostgreSQL 18+ (uses `uuidv7()`), Redis,
S3 via django-storages, social-auth-app-django, basecoat CSS (via PostCSS
with wireit).

## Core commands & workflows

- `uv sync` — install dependencies. **Use `uv` only**, never `pip`.
- `npm install` — install Node.js dependencies (Tailwind, basecoat, PostCSS, wireit).
- `npm run build` — compile CSS via PostCSS (`src/css/app.css` → `root/static/css/app.css`).
- `npm run dev` — watch and recompile CSS on change.
- `uv run python manage.py check` — Django system checks.
- `uv run python manage.py makemigrations` — generate migrations.
- `uv run python manage.py migrate` — apply migrations.
- `uv run python manage.py runserver` — dev web server.
- `uv run python manage.py dns` — start DNS server.
- `uv run python manage.py smtp` — start SMTP server.
- `uv run pre-commit run --all-files` — lint/format (ruff, djangofmt, pyupgrade,
  mdformat, dockerfmt).
- `uv run ruff check --fix . && uv run ruff format .` — ruff only.
- `docker compose up -d` — all services via Docker Compose.

## Rules, constraints & safety

- **Never read or expose `.env`, `.env.production`, or secrets.** These files
  contain real OAuth secrets, DB passwords, and Redis passwords.
- **Use `uv` exclusively** for dependency management — never `pip install`.
- **PostgreSQL 18+ required** — `db_default` uses the `uuidv7()` function.
- **Do not write tests** — the test suite is planned but not yet started.
  Linting/formatting via pre-commit is the current quality gate.
- **Update `CONVENTIONS.md`** when a reviewer identifies a new convention or
  corrects a pattern. This file is the authoritative coding-conventions source.
- **`root/views.py` must not import models from other first-party apps.**
  Cross-app views belong in their corresponding app.
- **`Model.save()` must include `update_fields=`** to avoid race conditions.
- **No private functions** (underscore prefix) — this project is not for
  redistribution.
- **Follow `CONVENTIONS.md`** for all coding patterns (URLs, PKs, fields,
  control flow, imports, naming).

## Quality, testing & definition of done

Before you finish, always:

- Run `uv run python manage.py check` — must pass with zero issues.
- Run `uv run pre-commit run --all-files` — must pass (ruff, djangofmt, and more).
- Run `uv run python manage.py makemigrations --check --dry-run` — verify no
  missing migrations for model changes.
- Verify that URL reversals work for any changed or added routes.
- Update `CONVENTIONS.md` if a review introduces a new convention.
- Follow the `naming-things` guidelines:
  `curl -sSL https://raw.githubusercontent.com/codingjoe/naming-things/refs/heads/main/README.md | cat`

## Browser automation

Playwright MCP (`.mcp.json`) runs headless and writes screenshots to
`.playwright-mcp/`. The dev server binds to a random localhost port — read
it from the `runserver` output, then navigate to `http://localhost:<port>`.

The MCP server loads `.playwright-mcp-config.json` (via `--config`)
for `headless` and `outputDir`; no request headers are required (dev
requests are auto-authenticated as the bundled `test` superuser).

## Test data

Bundle: one user (`test`, password `test`), one org (`acme`), one domain
(`acme.com`), one SMTP credential, three outgoing messages, three
transmissions, three SigningKeys. Load with
`manage.py loaddata fixtures/initial_data.json`. Refresh with:

1. Wipe the database and re-apply migrations:
   `rm -f db.sqlite3 && uv run python manage.py migrate`
1. Seed the rows via the ORM (see `tx_mail/management/commands/seed_test_data.py`):
   `uv run python manage.py seed_test_data`
1. Regenerate the fixture from the seeded DB:
   `uv run python manage.py dumpdata auth accounts kms domains tx_mail smtp --output fixtures/initial_data.json`
1. Format the JSON via the `pretty-format-json` pre-commit hook.

The `tx_mail` app is included because `OutgoingMessage` inherits from
`Message` via multi-table inheritance: the parent rows must be loaded
before the child rows, otherwise `loaddata` fails on a missing
`tx_mail_message.id` foreign key.

## Pointers to further documentation

- `CONVENTIONS.md` — authoritative coding conventions (URLs, PKs, model fields,
  save patterns, control flow, imports, authentication, naming).
- `README.md` — setup guide, architecture overview, app dependency graph,
  free sender domain docs.
- `REVIEW.md` — the reviewer's standing rules (conventions, dependency
  direction). `CLAUDE.md` and `.github/copilot-instructions.md` symlink to it.
- `root/settings.py` — all `RELAY_*` config and environment variables.
- `legal/docs/` — legal page Markdown sources (imprint, privacy, terms).

## Examples

**Good:** Add a field to `OutgoingMessage` with `verbose_name` and `help_text`.
Then do the following steps:

1. Generate a migration.
1. Run `manage.py check` and `makemigrations --check`.
1. Verify that `CONVENTIONS.md` does not need an update.

**Bad:** Import a model from `domains` in `root/views.py`, use `pip install`
for a dependency, or save a model without `update_fields=`.
