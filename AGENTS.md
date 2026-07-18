# Agent Instructions

## Project overview

Relay is a B2B SaaS communication platform (email, VoIP, and more) on
Django 6.0 / Python 3.14. The key feature: a **built-in authoritative
nameserver** so users only set NS delegation + DMARC — MX, SPF, DKIM,
and Return-Path are served automatically. GitHub OAuth for auth.

## Architecture & tech stack

Three services from one codebase, each a separate Docker container:

- **Web** — Django web UI + admin (Granian ASGI in prod, `runserver` in dev).
- **DNS** — Authoritative nameserver (dnslib, UDP+TCP). `nameserver/resolver.py`
  builds DNS records from `Domain` model properties — no zone files.
- **SMTP** — Inbound/outbound mail (aiosmtpd). `smtp/handlers.py` receives,
  authenticates via `Credential`, stores raw body as `FileField`, dispatches
  delivery via Django task framework.

Apps: `root` (settings, root URLs, base templates — no cross-app model imports),
`accounts` (OAuth + SMTP credentials), `domains` (Domain, DkimKey, DNS
verification, dashboard), `mail` (Message, Transmission, delivery task),
`nameserver` (resolver, server, DNS verification services), `smtp` (server,
handlers, DKIM signing), `legal` (Markdown legal pages), `abstract` (shared
TimeStamped model, admin mixins, Markdown utils).

Key tech: Django 6.0 task framework, PostgreSQL 18+ (uses `uuidv7()`), Redis,
S3 via django-storages, social-auth-app-django, Primer CSS.

## Core commands & workflows

- `uv sync` — install dependencies. **Use `uv` only**, never `pip`.
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
- Run `uv run pre-commit run --all-files` — must pass (ruff, djangofmt, etc.).
- Run `uv run python manage.py makemigrations --check --dry-run` — verify no
  missing migrations for model changes.
- Verify URL reversals work for any changed/added routes.
- Update `CONVENTIONS.md` if a review introduces a new convention.
- Follow the `naming-things` guidelines:
  `curl -sSL https://raw.githubusercontent.com/codingjoe/naming-things/refs/heads/main/README.md | cat`

## Pointers to further documentation

- `CONVENTIONS.md` — authoritative coding conventions (URLs, PKs, model fields,
  save patterns, control flow, imports, auth, naming).
- `README.md` — setup guide, architecture overview, env var reference,
  free sender domain docs.
- `.github/copilot-instructions.md` — detailed architecture and app-by-app
  guide for AI coding assistants.
- `root/settings.py` — all `RELAY_*` config and environment variables.
- `docs/` — legal page Markdown sources (imprint, privacy, terms).

## Examples

**Good:** Add a new field to `Message` with `verbose_name` and `help_text`,
generate a migration, run `manage.py check` + `makemigrations --check`,
verify `CONVENTIONS.md` doesn't need updating.

**Bad:** Import a model from `domains` in `root/views.py`, use `pip install`
for a dependency, or save a model without `update_fields=`.
