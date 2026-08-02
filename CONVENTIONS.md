# Coding Conventions

This document records coding conventions for the Relay project.
Update it based on review feedback.

## URLs

- Use the `app:model-CRUD` naming pattern with hyphens (for example, `org-list`,
  `org-detail`, `org-create`, `domain-verify`, `message-list`). This mirrors
  DRF's router convention.

- Use nested `include()` for cascaded paths:

  ```python
  path(
      "credentials/",
      include(
          [
              path("new", ...),
          ]
      ),
  )
  ```

- CRUD actions on objects must **not** end with a trailing slash.
  List/create views can use a trailing slash.

- Always reference URLs by name, never by hardcoded path — in settings
  (`LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL`), `redirect()`,
  `reverse()`/`reverse_lazy()`, and templates (`{% url %}`). This keeps
  redirects valid when paths move.

- Use `param_replace` (from `abstract` template tags) to build filtered
  pagination URLs: `href="?{% param_replace page=page_obj.next_page_number %}"`.
  Never hand-construct query strings in templates.

## Primary Keys

- Prefer `BigAutoField` (bigint) for most models — easier to work with in Django.
- Use slugs based on title for URL patterns, not UUIDs.
- Exception: `Message` and `Transmission` use UUIDv7 as PK because IDs are
  used as SMTP message-ids and need to be unique/transferable outside Postgres.
- Use `db_default` with a PostgreSQL database function (for example, `UuidV7()`) for
  database-side UUIDv7 generation, alongside the Python `default=uuid.uuid7`
  for ORM-level defaults.
- Models with a FK to a message model (for example, `DmarcRecord`, `TlsFailure`,
  `WebhookDelivery`) must use UUIDv7 PK too. A Django system check
  (`abstract.W001`) warns if a model with a FK to a UUID-PK model uses a
  non-UUID primary key.

## Model Fields

- All fields must have `verbose_name` and `help_text` (except FK and PK).
- Use `db_defaults` where a database-side default is appropriate.
- Drop `class Meta` entirely if it only inherits without overriding anything.
- Use `TextField` instead of `CharField` for all fields unless you
  specifically want Django's `max_length` validation. In PostgreSQL there
  is no performance advantage to `varchar` over `text` — both use the same
  storage. Choice fields use `TextField` with `choices=`. Django's choice
  validation works without `max_length`. Only use `CharField(max_length=N)`
  when the standard defines a fixed maximum length and you want the DB-level
  check constraint (for example, `EmailField` which is `CharField(max_length=254)`
  per RFC 5321).

## Model.save()

- Always include explicit `update_fields=` to avoid race conditions and be explicit.
- Use `force_insert=True` when creating a new instance.

## Functions

- No private functions (underscore prefix) — this project is not for redistribution.
- Function names must be descriptive, not ambiguous.

## Docstrings

- Use Google-style Markdown docstrings (Napoleon). Not RST.
- Start with a verb describing the external behavior (for example, "Return",
  "Send", "Validate", "Determine").
- Keep docstrings concise — one sentence for simple functions.
- Never repeat the function/method name in the docstring.
- Never describe implementation details — describe what, not how.
- Use bullet lists for parameters only when the function has 3+ non-obvious
  parameters. Otherwise the signature is self-documenting.
- Do NOT use double backticks (` ` `) for inline code — use single backticks (` \` \`\`). Double backticks are RST syntax, not Markdown.
- Do not write docstrings for inherited methods or properties — the
  base class already documents them.
- Do not write module docstrings for common Django/Python files
  (`models.py`, `admin.py`, `views.py`, `urls.py`, `apps.py`, `tasks.py`,
  `signals.py`, `tests.py`). The file name is self-documenting.

## Control Flow

- Prefer `match`/`case` statements over if-chains where applicable.
- Use `.get()` with EAFP (try/except) instead of `.first()` with a `None`
  check. Use `get_object_or_404()` in views to convert `DoesNotExist` to
  `Http404` automatically.

## Imports

- All imports at the top of a file, except inside Celery/Django tasks where
  late imports are needed to avoid import cycles.
- Import views as `from . import views` in URL configs, then reference
  `views.MyView.as_view()`.
- Do not import with different names (no `import x as y`) unless necessary.
- Do not import per-property — import the module directly.

## Authentication

- Use `social-auth-app-django` (python-social-auth) for OAuth providers
  instead of custom OAuth code.
- Custom pipeline steps live in `accounts/pipelines.py`.

## Naming

- Use names that cover both ingress and egress when a model tracks
  bidirectional events (for example, `Transmission`, not `Delivery`).
- Avoid abbreviations in general — write names out in full (for example,
  `nameserver`, not `ns`). This includes field names, verbose names,
  and help text.
- Email-specific abbreviations are OK since they are more common than
  their long forms: SPF, DKIM, DMARC, MX, SMTP, PTR.
- Use `...` instead of `pass` in empty classes.

## Templates & UI

- Use [basecoat-css](https://basecoatui.com/) (maia style) for all UI styling.
  Do **not** use pico.css or any other CSS framework.

- Use Django template inheritance: define the shell once in
  `root/templates/base.html` and have every page template `{% extends "base.html" %}`.
  Pages only override `{% block title %}` and `{% block content %}`.

- For interactive widgets, prefer off-the-shelf basecoat components over custom
  CSS or custom JS:

  - Buttons: `<button class="btn" data-variant="secondary|ghost|destructive" data-size="sm|icon|default">`.
    Use `data-variant="secondary"` for most non-primary buttons. Reserve
    `data-variant="outline"` for `item` elements (outlined cards), never for
    buttons inside a `button-group`. Use `data-variant="destructive"` for
    delete/remove actions. Omit `data-variant` entirely for the primary
    action in a group.
  - Cards: `<article class="card">`.
  - Tables: wrap in `<div class="table-container"><table class="table">`.
  - Dialogs: `<dialog class="dialog"><div><header>…<section>…<footer>…</div></dialog>`,
    open with `.showModal()` and close with `.close()`.
  - Form controls: `<input class="input">`, `<select class="select w-full">`,
    `<textarea class="textarea">`. Always pair form controls with `w-full` so
    they fill the field width inside dialogs and filter rows. Wrap each form
    in `<fieldset class="fieldset">` and each field in
    `<div role="group" class="field">` with a native `<label for="id_x">…</label>`
    linked to the control via `id="id_x"`. The `.field` container provides
    spacing and error styling. Native controls auto-style. Do not nest inputs
    inside `<label>` or use `<span class="label">` for the label text.
  - Dropdown menus: `<div class="dropdown-menu" id="…">` with a trigger button.
  - Avatars: `<span class="avatar" data-size="sm"><img …><span>CN</span></span>`.
  - Badges: `<span class="badge" data-size="sm" data-variant="primary|outline|destructive">`.
    Map status semantics to variants consistently across the app:
    successful states (`sent`, `delivered`, `received`) → `primary`;
    in-flight or neutral states (`pending`, `held`, `retry`,
    `webhook_sent`) → `outline`;
    failure states (`bounced`, `dropped`, `failed`,
    `webhook_failed`) → `destructive`.
  - Items: use basecoat's `<a class="item" data-variant="outline">` (or
    `<article class="item">`) inside a `<div class="item-group">` for list
    pages that show selectable entities (for example, organizations). Prefer items
    over tables when each row is a single clickable entity with a title and
    short metadata.
  - Brand name: write `relay` in lowercase everywhere — it is a brand name,
    not a translatable string. Do not wrap it in `{% translate %}` or
    apply `|capfirst`/`|title`.

- Icons use [Lucide](https://lucide.dev/) via vanilla JS — load the UMD
  bundle from a CDN with `defer` and call `lucide.createIcons()` on
  `DOMContentLoaded`. Render icons with `<i data-lucide="name" class="size-4|size-5|size-3.5" aria-hidden="true">`
  (Tailwind size scale: 3.5=14px, 4=16px, 5=20px). Never inline Lucide SVGs
  by hand — the library replaces the `<i>` element with the SVG at runtime.
  Never use unicode emoji (✅, ❌, ⏳, 📬) for status or decorative icons —
  use Lucide icons with semantic color classes instead (for example,
  `circle-check` with `text-success`, `circle-x` with `text-destructive`,
  `circle-dashed` with `text-muted-foreground`).

- CSS is built with [PostCSS](https://postcss.org/) and [wireit](https://github.com/google/wireit).
  The source entry is `src/css/app.css` — it imports Tailwind CSS v4 and
  basecoat-css (maia style), plus any custom CSS variables and layout glue.
  Run `npm run build` to compile `src/css/app.css` → `root/static/css/app.css`
  (a build artifact, gitignored — do not edit it directly). Run `npm run dev`
  to watch for changes during development. The build output is served via
  `{% static 'css/app.css' %}` in `base.html`.
  Custom CSS is kept to the bare minimum — use it only for layout glue
  basecoat/Tailwind do not provide directly (for example, the breadcrumb
  container's background, marketing-page accent highlights). Do not use it
  for component styling — use basecoat classes instead. If a utility is
  missing, prefer a Tailwind utility before adding a custom rule.

- Django form widgets are styled by overriding templates under
  `abstract/templates/django/forms/widgets/{input,checkbox,select,textarea}.html`.
  Each override adds the matching basecoat class
  (`input`, `checkbox`, `select`, `textarea`) while preserving any custom
  `widget.attrs` the form supplies. Prefer rendering forms with
  `{{ form }}` / `{{ form.field }}` so the overrides apply automatically.
  Only fall back to hand-written inputs when a widget truly needs custom
  markup.

- Sidebar and main-nav links: assign each URL to a variable with
  `{% url '...' as var %}`, then use exact `request.path == var` to set
  `aria-current="page"`. Do **not** use `{% if var in request.path %}` —
  a substring check highlights parent links on every child page.
  Hide main-nav links entirely when no org is selected.

- Breadcrumbs: use `BreadcrumbViewMixin` from `abstract.views`. Each view
  sets `title` (the breadcrumb title) and `parent` (the URL name of the
  parent page). The mixin builds the chain by traversing parents via
  `get_url(cls, request)` and `get_title(cls, request)` classmethods.
  Override `get_title` for request-dependent titles (for example, the org name
  from `request.current_org`). Override `get_url` for URL patterns that
  need request kwargs (for example, `OrganizationScopedView` passes `org_slug`).
  For detail views with no `title`, the breadcrumb falls back to
  `str(self.object)`. Context variable is `breadcrumbs`, dict keys are
  `{"title": ..., "url": ...}`.

- Tailwind v4's preflight resets `a { color: inherit }`. Add
  `class="link"` to entity anchors so they get primary color and
  underline from `src/css/app.css`.

## Testing

- Use `pytest.mark.django_db` (not the `db` fixture) when a test needs the
  database. This marker allows running non-DB tests in isolation:

  ```bash
  uv run pytest -m "not django_db"
  ```

- Tests that do not need the database carry no marker.

- Prefer unit tests over integration tests — test model methods and
  utility functions without the DB where possible.

- CRUD view tests use Django's test client via the pytest-django `client`
  fixture. Use `client.force_login(user)` for authenticated requests.

- Test names follow a double-underscore convention:

  - Unit tests mirror the function/property name:
    `test_fn__arbitrary_suffix` (for example, `test_verify_key__wrong_key`,
    `test_salt__returns_class_path`).
  - View tests include the HTTP method:
    `test_get__arbitrary_suffix` / `test_post__arbitrary_suffix`
    (for example, `test_get__not_found`, `test_post__creates_org`).

- Group related tests in classes — no comment headlines (`# ── … ──`).
  Use plain `class TestSomething:` with no decorator unless a class-level
  `@pytest.mark.django_db` is needed.

- One test per scenario. Do not write parametrised mega-tests that obscure individual
  assertions.

- Avoid mocking and patching unless the code under test performs external I/O
  (DNS lookups, SMTP delivery, HTTP requests). Mocks can diverge from the real
  implementation — tests pass but production fails. Prefer real objects and
  real database state.

- Test modules do not need module docstrings.

- Use `pytest.mark.asyncio` for async test methods (pytest-asyncio is
  installed).

## Multi-table inheritance

- When sibling models share most columns, promote the shared columns
  to a concrete parent. Per-kind fields stay on the children.

- Indexes on shared columns live on the parent's `Meta.indexes`.
  Per-kind indexes stay on the child.

- A `content_type` FK to `ContentType` records the subclass for each
  row. Each child sets it in `save()` via
  `ContentType.objects.get_for_model(type(self))`.

## Merged list views

- Place merged views in the parent app that depends on all siblings.
  Siblings must not import from each other.

- Legacy list URLs redirect to the merged view. Put the redirect
  view in each sibling's own `views.py` to avoid circular imports.

## App structure

- A concrete model shared between sibling apps belongs in a dedicated
  app, not in `abstract`. The `abstract` app stays non-materialized.

- The shared app owns the merged list views and the template-tag
  library. Siblings keep their own detail views.
