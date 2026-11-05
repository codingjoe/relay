# Agent Instructions

## Dependencies

Apps must not import their dependents. The contracts live in
`pyproject.toml` (`[tool.importlinter]`). Run `lint-imports` after changing
the graph.

## Core commands & workflows

- `uv sync`. Install dependencies. Use `uv` only, never `pip`.
- `pnpm install`. Install Node.js dependencies.
- `pnpm run build`. Compile CSS and vendor ES modules.
- `pnpm run dev`. Watch and rebuild CSS and ES modules.
- `uv run python manage.py check`. Django checks.
- `uv run python manage.py makemigrations`. Generate migrations.
- `uv run python manage.py migrate`. Apply migrations.
- `uv run python manage.py runserver`. Dev web server.
- `uv run python manage.py dns`. Start DNS.
- `uv run python manage.py msa`. Start MSA.
- `uv run python manage.py mta`. Start MTA.
- `prek run --all-files`. Lint and format.
- `uv run ruff check --fix . && uv run ruff format .`. Ruff only.
- `pnpm install && pnpm run build && uv run python manage.py collectstatic --noinput --no-esm`.
  Must run before Django checks and template tests.

## Rules, constraints & safety

- **Never read or expose `.env`, `.env.production`, or secrets.**
- **Use `uv` only.** Never `pip install`.
- **PostgreSQL 18+ is required.** `db_default` uses `uuidv7()`.
- **Update the relevant `AGENTS.md`** when a reviewer identifies a convention.
- **Update `docs/docs/`** when behavior changes.
- **Label every issue** with one lane and one tag, `<tag>: <lane> <what>.`
  Lanes: `sec`, `bug`, `perf`, `naming`, `bloat`, `doc`, `test`, `deps`.
  Tags: `side quest`, `sus`, `real`, `cap`, `receipts`, `yeet`, `duh`, `NPC`,
  `cringe`, `glow up`, `ghost`, `delulu`, `kept`, `dropped`.
- **Do not run tests or pre-commit unless asked.** `manage.py check` and
  `makemigrations --check --dry-run` are fine.
- **Review against the `AGENTS.md` files** and the import-linter contracts.

## URLs

- Use the `app:model-CRUD` naming pattern with hyphens, for example
  `org-list`, `org-detail`, `message-list`.
- Use nested `include()` for cascaded paths. CRUD actions on objects do not
  end with a trailing slash. List and create views can.
- Reference URLs by name, never by hardcoded path. Use `reverse()`,
  `redirect()`, and `{% url %}`.
- Use `{% querystring %}` for filtered pagination. Never build query strings
  by hand.

## Tasks

- Declare the queue on the task: `@task(queue_name="...")`.
- Return `None`. Backends serialize the return value, so a model or `UUID`
  records a failed run for work that succeeded.
- Retry with `threadmill.retry.ExponentialBackoff`. Finalize non-final states
  in the retry callback.
- Name `AcknowledgementTimeout` in `expected_exceptions` when a task may run
  again after its worker died.
- Add new queues to `TASK_QUEUES` in `root/settings.py` and to the worker
  commands in `deploy/k8s/web.yaml`. Mail pipeline queues go before `default`.

## Test conventions

- Use `pytest.mark.django_db` (not the `db` fixture) when a test needs the
  database. Tests without the database carry no marker.
- Prefer unit tests. Test model methods and utility functions without the DB.
- CRUD view tests use the pytest-django `client` fixture and
  `client.force_login(user)`.
- Name unit tests `test_fn__suffix`. Name view tests
  `test_get__suffix` / `test_post__suffix`.
- One test per scenario. A test asserts behavior this codebase owns, not a
  framework default.
- Use plain `class TestSomething:` with no decorator unless a class-level
  `@pytest.mark.django_db` is needed.
- Avoid mocking unless the code performs external I/O. Prefer real objects
  and real database state. Use `pytest.mark.asyncio` for async tests.

## App structure

- A concrete model shared between sibling apps belongs in a dedicated app,
  not in `abstract`. `abstract` stays non-materialized.
- The shared app owns the merged list views and the template-tag library.
  Siblings keep their own detail views.
- Place merged views in the parent app that depends on all siblings. Siblings
  must not import each other.

## Quality, testing & definition of done

Before you finish:

- Run `uv run python manage.py check`. Zero issues.
- Run `uv run python manage.py makemigrations --check --dry-run`.
- Verify URL reversals for changed or added routes.
- Follow the naming-things guidelines:
  `curl -sSL https://raw.githubusercontent.com/codingjoe/naming-things/refs/heads/main/README.md | cat`

## Browser automation

Use Playwright MCP headless. Write screenshots to `.playwright-mcp/`.
Read the dev server port from the `runserver` output.

Disable the browser cache before capturing screenshots
(`Network.setCacheDisabled` via CDP). Conditional GETs answer `304`, so the
browser would otherwise reuse stale HTML with the debug toolbar.

Refresh homepage screenshots (`root/static/img/email-*-{light,dark}.png`)
from the message log and a message detail at 1182x788, device scale factor 1.
Shift fixture timestamps forward first, or the 30-day chart renders empty.

## Examples

**Good:** Add a field to `OutgoingMessage` with `verbose_name` and `help_text`.
Generate a migration. Run `manage.py check` and `makemigrations --check`.

**Bad:** Import a `domains` model in `root/views.py`, use `pip install`, or
save without `update_fields=`.
