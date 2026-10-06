# Coding Conventions

This document records coding conventions for the Relay project.
Update it based on review feedback.
A rule lives either in this document or in `.relint.yml`, never both.

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

- Always reference URLs by name, never by hardcoded path. In settings
  (`LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL`), `redirect()`,
  `reverse()`/`reverse_lazy()`, and templates (`{% url %}`). This keeps
  redirects valid when paths move.

- Use `param_replace` (from `abstract` template tags) to build filtered
  pagination URLs: `href="?{% param_replace page=page_obj.next_page_number %}"`.
  Never hand-construct query strings in templates.

## Primary Keys

- Prefer `BigAutoField` (bigint) for most models. Easier to work with in Django.
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
- Index fields used for ordering. A field listed in `Meta.ordering` needs an
  index (for example, `SpamCheck.started_at`).
- Drop `class Meta` entirely if it only inherits without overriding anything.
- Use `TextField` instead of `CharField` for all fields unless you
  specifically want Django's `max_length` validation. In PostgreSQL there
  is no performance advantage to `varchar` over `text`. Both use the same
  storage. Choice fields use `TextField` with `choices=`. Django's choice
  validation works without `max_length`. Only use `CharField(max_length=N)`
  when the standard defines a fixed maximum length and you want the DB-level
  check constraint (for example, `EmailField` which is `CharField(max_length=254)`
  per RFC 5321).

## Model.save()

- Always include explicit `update_fields=` to avoid race conditions and be explicit.
- Use `force_insert=True` when creating a new instance.

## Functions

- Function names must be descriptive, not ambiguous.
- Do not write one-liner functions that only wrap a single expression. Inline
  the expression at its call site.
- Use generator functions when a function produces a sequence for lazy
  consumption, for example when walking database relations.

## Comments

- Comment only when the code is unexpected or hard to read. A comment that
  restates the line beneath it is a defect.
- Never explain configuration in prose. For a setting, add a single link to
  the documentation page for that setting or that service, and keep only the
  fact a reader cannot get from the docs, for example
  `# rspamd pools the A records, see https://docs.rspamd.com/configuration/upstream/`.
- Write every comment as one line. Keep the reasoning that stops a later edit
  from undoing a fix, rather than dropping it.
- Prefer a trailing annotation on an unexpected literal to a block above it,
  for example `"40M" # above the 2**25 SMTP DATA limit`.

## Docstrings

- Use Google-style Markdown docstrings (Napoleon). Not RST.
- Start with a verb describing the external behavior (for example, "Return",
  "Send", "Validate", "Determine").
- Keep docstrings concise. One sentence for simple functions.
- Never repeat the function/method name in the docstring.
- Never describe implementation details. Describe what, not how.
- Use bullet lists for parameters only when the function has 3+ non-obvious
  parameters. Otherwise the signature is self-documenting.
- Do not write docstrings for inherited methods or properties. The
  base class already documents them.

## Control Flow

- Prefer `match`/`case` statements over if-chains where applicable.
- No early returns. Exit a function from a single `return` statement at the
  end. `.relint.yml` enforces the bare `return` and `continue` subset.
- Use `.get()` with EAFP (try/except) instead of `.first()` with a `None`
  check. Use `get_object_or_404()` in views to convert `DoesNotExist` to
  `Http404` automatically.

## Imports

- Import views as `from . import views` in URL configs, then reference
  `views.MyView.as_view()`.
- Do not import with different names (no `import x as y`) unless necessary.
- Do not import per-property. Import the module directly.

## Authentication

- Use `social-auth-app-django` (python-social-auth) for OAuth providers
  instead of custom OAuth code.
- Custom pipeline steps live in `accounts/pipelines.py`.

## Tasks

- Declare the queue on the task itself, so the pipeline stage is visible at
  the definition: `@task(queue_name="ingress")`.
- Pick the queue by pipeline stage: `ingress` for received mail, `egress`
  for outgoing submissions, `delivery` for SMTP delivery to remote MX hosts,
  and `default` for everything else.
- Return `None` from tasks: backends serialize the return value, so a model
  instance or a `UUID` records a failed run for work that succeeded.
- Add new queues to `TASK_QUEUES` in `root/settings.py` and to the worker
  commands in `deploy/k8s/web.yaml`, with the mail pipeline queues ahead of
  `default`. A task whose queue is missing from the settings raises at import
  time.

## Naming

- Use names that cover both ingress and egress when a model tracks
  bidirectional events (for example, `Transmission`, not `Delivery`).
- Avoid abbreviations in general. Write names out in full (for example,
  `nameserver`, not `ns`). This includes field names, verbose names,
  and help text.
- Email-specific abbreviations are OK since they are more common than
  their long forms: SPF, DKIM, DMARC, MX, SMTP, PTR.
- Do not wrap technical protocol terms in `gettext`, for example STARTTLS,
  TLS, or plaintext. They read the same in every language.

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
  - Cards: `<article class="card">`. Never nest a card inside another card.
    Group content within a card using headings, `<hr>`, or padded blocks.
  - Tables inside cards sit flush with the card edges: use
    `<article class="card gap-0 p-0 overflow-hidden">`, put the preceding
    content (heading, metadata) in an inner `<div class="px-6 pt-6">` block,
    and place the `<div class="table-container">` directly inside the card.
  - Do not put counter badges in section headings (for example,
    `Headers 6`). The section content is directly below; a count adds noise,
    not information.
  - Tables: wrap in `<div class="table-container"><table class="table">`.
  - Dialogs: `<dialog class="dialog"><div><header>…<section>…<footer>…</div></dialog>`,
    open with `.showModal()` and close with `.close()`.
  - Translatable strings. Msgids start lowercase. `|capfirst` and `|title`
    set the display casing. A msgid that renders without a casing filter is a
    sentence, so it starts with a capital letter. Sentences after the first
    inside a msgid also start with a capital letter, because no filter reaches
    them.
  - Form controls: `<input class="input">`, `<select class="select w-full">`,
    `<textarea class="textarea">`. Always pair form controls with `w-full` so
    they fill the field width inside dialogs and filter rows. Wrap each form
    in `<fieldset class="fieldset">` and each field in
    `<div role="group" class="field">` with a native `<label for="id_x">…</label>`
    linked to the control via `id="id_x"`. The `.field` container provides
    spacing and error styling. Native controls auto-style. Do not nest inputs
    inside `<label>` or use `<span class="label">` for the label text.
  - Browser autocomplete: give a field that holds the member's own data the
    matching token (`autocomplete="email"`, `name`, `url`, `tel`,
    `new-password`, `one-time-code`) so the browser fills the right value
    instead of guessing from the field name. Set `autocomplete="off"` where a
    suggestion would be wrong: a search or filter box, which takes a query
    rather than the member's data, or a value that belongs to someone else,
    such as the third-party address on the suppression list. A free-text label
    the member invents, such as a credential name, needs neither.
  - Dropdown menus: `<div class="dropdown-menu" id="…">` with a trigger button.
  - Avatars: `<span class="avatar" data-size="sm"><img …><span>CN</span></span>`.
  - Badges: `<span class="badge" data-size="sm" data-variant="primary|outline|destructive">`.
  - Tooltips: use the basecoat `data-tooltip` attribute on any element.
    Do not use native `title` attributes for tooltips.
  - Items: use basecoat's `<a class="item" data-variant="outline">` (or
    `<article class="item">`) inside a `<div class="item-group">` for list
    pages that show selectable entities (for example, organizations). Prefer items
    over tables when each row is a single clickable entity with a title and
    short metadata.
  - Brand name. Write `relay` in lowercase everywhere. It is a brand name,
    not a translatable string. Do not wrap it in `{% translate %}` or
    apply `|capfirst`/`|title`.

- Icons use [Tabler](https://tabler.io/icons) through its SVG sprite. Render
  them with `{% tabler name="copy" size="3.5" %}` after `{% load abstract %}`.
  The tag fills `abstract/templates/abstract/tabler.html`, which writes
  `<svg class="tabler size-3.5" aria-hidden="true"><use href="…"></use></svg>`
  and resolves the sprite URL once per process. The tag adds the `tabler`
  class and the size, so neither is repeated at the call site. Pass extra
  utilities as `class="…"`, for example
  `{% tabler name="chevron-right" class="text-muted-foreground ms-auto" %}`,
  and `size=None` for an icon that takes its size from CSS. Every icon needs
  one of the two: the sprite symbols carry no width or height, and basecoat
  sizes an icon only where a component draws one itself, such as a badge
  (12px, forced) or a modal close button (16px). Extra attributes are keyword
  arguments with underscores for dashes, for example `data_tooltip="…"`. The
  sprite is the vendored
  `root/static/img/tabler-icons/tabler-sprite.svg` that ships with
  the `@tabler/icons-sprite` dev dependency, so icon names come straight from
  tabler.io/icons and nothing is generated per icon. Sizes follow the
  Tailwind scale on the icon (`size-3`=12px, `3.5`=14px, `4`=16px, `5`=20px,
  `6`=24px, `8`=32px). The tag builds `size-<size>` at render time, so
  `src/css/app.css` safelists the scale with `@source inline(...)`; add a
  size there when the tag gains one. `src/css/base.css` keeps `svg.tabler`
  inline with its label and scales it by 1.1, because Tabler draws inside a
  3px inset where Lucide drew inside 2px. Never write the `svg` element by
  hand and never ship a placeholder attribute for the client to replace.
  Never use unicode emoji (✅, ❌, ⏳, 📬) for status or decorative icons - use
  Tabler icons with semantic color classes instead (for example,
  `#tabler-circle-check` with `text-primary`, `#tabler-circle-x` with
  `text-destructive`, `#tabler-circle-dashed` with `text-muted-foreground`).

- CSS is built with [PostCSS](https://postcss.org/) and [wireit](https://github.com/google/wireit).
  The source entry is `src/css/app.css`, which imports Tailwind CSS v4,
  basecoat-css (maia style), and the partials next to it: `theme.css` (design
  tokens), `base.css` (preflight fixes), `components.css` (basecoat
  overrides), and `syntax.css` (the Pygments and MicroLighter palettes). Put a
  new rule in the partial it belongs to rather than the entry.
  Run `pnpm run build` to compile `src/css/app.css` → `root/static/css/app.css`
  (a build artifact, gitignored. Do not edit it directly). Run `pnpm run dev`
  to watch for changes during development. The build output is served via
  `{% static 'css/app.css' %}` in `base.html`. The same build vendors the ES
  modules, which is why `collectstatic` runs with `--no-esm`.
  Custom CSS is kept to the bare minimum. Use it only for layout glue
  basecoat/Tailwind do not provide directly (for example, the breadcrumb
  container's background, marketing-page accent highlights). Do not use it
  for component styling. Use basecoat classes instead. If a utility is
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
  `aria-current="page"`. Do **not** use `{% if var in request.path %}` -
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
  underline from `src/css/base.css`.

- Code samples shown on a page live as real source files under
  `root/templates/snippets/` (`.py`, `.js`, `.ts`), so ruff and esupgrade lint
  them. The template pulls one in with
  `{% filter force_escape %}{% include "snippets/name.py" %}{% endfilter %}`.

- Scripts live in static ES modules, never inline in a template. A page loads
  its module with `{% esm '#js/app.js' %}` (load the `esm` tag library in that
  template), which resolves the specifier through the import map and writes the
  bundle URL with the integrity hash the browser verifies. A form that needs a
  module puts `django_esm.forms.ESM` in its `Media`, never a hand-written tag.
  Pass per-render data with `json_script` or `data-*` attributes. Shared UI
  behavior lives in `root/static/js/app.js` and is driven by data hooks on the
  markup: `data-dialog`, `data-dialog-close`, `data-backdrop-close`,
  `data-auto-open`, `data-confirm`, `data-copy`, `data-share`, `data-href`,
  `data-toggle`, `data-select`, `data-mirror`.

- Third-party JavaScript comes from npm, never from a CDN. Import it by
  package name (`import { html } from "lit"`) and let the import map
  (`{% importmap %}` in `base.html`) resolve it: `pnpm run build` vendors the
  `dependencies` from `package.json` into `staticfiles/esm` via
  [esimport](https://github.com/codingjoe/esimport). List every first-party
  module that imports a package in the `imports` map of `package.json`
  (`#js/*`, `#abstract/*`, `#message/*`). `esimport --treeshake` starts from
  those entries, so it keeps the package entry points they reach and drops the
  rest. Add a package with `pnpm add`; the import map picks it up on the next
  build.

## Admin

- List every editable foreign key and many-to-many field in
  `autocomplete_fields`. The change form must never render a select box over
  a whole table. The related admin needs `search_fields` and the related
  model its own admin, or Django's checks fail. `abstract.W004` warns about
  a missing autocomplete.

## Views & Queries

- Publicly cacheable views (`public: True`) render the static chrome
  (`request.public_cache`): no user menu, no toasts, no org switcher. The
  response carries no `Vary: Cookie` and no queries.
- Forms, redirects, and template views answer `no-store`. A response without a
  `Cache-Control` header is stored by the Caddy edge cache for its 120s
  default and then served to every visitor.
- Revalidate with `ConditionalGetListMixin` when the page renders one queryset
  and nothing else, `ConditionalGetMixin` when a single object's `modified_at`
  covers the page. Both answer `private, max-age=5, must-revalidate`: the
  browser may reuse the page for a few seconds, and a write expires it on the
  next revalidation.
- Do not add context processors that provide querysets. Template chrome data
  (for example, `user_orgs`) comes from the view's mixin.
- Fetch a list once and derive counts, flags, and related objects from it
  instead of separate `count()`, `exists()`, and `get()` queries.
- `TimeStamped` models default to `models.FETCH_PEERS` (`FetchPeersManager`).
  Do not call `.fetch_mode()` in views.
- `TimeStamped.save()` persists `modified_at` on partial saves. Conditional
  GETs trust that timestamp, so a `QuerySet.update()` must pass
  `modified_at=timezone.now()` itself.

## Testing

- Use `pytest.mark.django_db` (not the `db` fixture) when a test needs the
  database. This marker allows running non-DB tests in isolation:

  ```bash
  uv run pytest -m "not django_db"
  ```

- Tests that do not need the database carry no marker.

- Prefer unit tests over integration tests. Test model methods and
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

- One test per scenario. Do not write parametrised mega-tests that obscure individual
  assertions.

- Group related tests in classes. No comment headlines (`# ── … ──`).
  Use plain `class TestSomething:` with no decorator unless a class-level
  `@pytest.mark.django_db` is needed.

- Avoid mocking and patching unless the code under test performs external I/O
  (DNS lookups, SMTP delivery, HTTP requests). Mocks can diverge from the real
  implementation. Tests pass but production fails. Prefer real objects and
  real database state.

- Test modules do not need module docstrings.

- Use `pytest.mark.asyncio` for async test methods (pytest-asyncio is
  installed).

## Multi-table inheritance

- When sibling models share most columns, promote the shared columns
  to a concrete parent. Per-kind fields stay on the children.

- When siblings share only a couple of columns, prefer an abstract base
  with concrete per-scenario models over multi-table inheritance. Put
  the shared behavior and fields on the base; concrete models implement
  abstract members and own the fields that differ.

- Indexes on shared columns live on the parent's `Meta.indexes`.
  Per-kind indexes stay on the child.

- A `content_type` FK to `ContentType` records the subclass for each
  row. The base `Message.save()` sets it via
  `ContentType.objects.get_for_model(type(self))`.

## Merged list views

- Place merged views in the parent app that depends on all siblings.
  Siblings must not import from each other.

## App structure

- A concrete model shared between sibling apps belongs in a dedicated
  app, not in `abstract`. The `abstract` app stays non-materialized.

- The shared app owns the merged list views and the template-tag
  library. Siblings keep their own detail views.

## Markdown docs apps

- Serve each markdown docs area from one app with a `docs/` folder.
  Extend `MarkdownArticleMixin` from `abstract.views`.

- Keep article slugs unique across all docs apps. The template loader
  resolves `<slug>.md` against every TEMPLATES DIRS entry in order, so a
  duplicate slug renders the wrong file.

- Keep `know_how/docs` brand-agnostic. Write relay-specific user docs in
  `docs/docs`.

- Write `docs/docs` for relay users, not developers. Environment variable
  names, setting keys, and other code references have no place there.
  Describe behavior and configuration in product terms: the platform
  domain, the dashboard, a submission host. Internal names such as
  `RELAY_*` belong in `README.md`.

## Kubernetes manifests

- Keep the manifests in `deploy/k8s/`, grouped by concern rather than one file
  per object. `kustomization.yaml` lists them.

- Put multi-line configuration in a real file rather than a block scalar in a
  manifest, and generate its ConfigMap from `kustomization.yaml`, the way
  `caddy/Caddyfile` does. The generated name carries a content hash, so editing
  the file changes the pod template and rolls the workload. A block scalar in a
  resource updates in place and leaves the running pods on the old
  configuration.

- Do not probe run-to-completion Job containers. `migration` and
  `clamav-updater` are legitimately long or quiet, and their health signal is
  the Job condition the deploy workflow already waits on; a probe would kill
  work in progress.

- Do not send `Host: localhost` from a probe. Django validates the header in
  `CommonMiddleware`, so a disallowed host answers 400 with a fully healthy app
  behind it, and the pod never becomes Ready. `web` is the only probe that
  reaches Django, and it sends the pinned `HOSTNAME`. Note that an `exec` probe
  does not run through the image entrypoint, so it sees the kubelet's
  environment and never a decrypted one.

- Give every container resource requests and limits.

- Add a startup probe only where boot is genuinely slow: `msa` and `mta` wait up
  to five minutes for certificate files, `clamav` loads its signature database,
  and `postgres` initialises a data directory. Everywhere else a liveness probe
  with a sensible `failureThreshold` is enough, and a startup probe is noise.

- Set `args`, not `command`, when overriding what a service runs. The images
  carry entrypoints (`/opt/venv/bin/python`, `/init`, `docker-entrypoint.sh`)
  that have to stay in place.

- Never put a credential in a ConfigMap. Where a config file needs one, commit
  it with a `${PLACEHOLDER}` and let the deploy workflow render a Secret. See
  `deploy/k8s/redis/` and `deploy/k8s/rspamd/`.

- Do not rely on `$(VAR)` expansion in a manifest. Kubernetes expands it only
  between a container's `env` entries, and never in `command` or `args`. Derive
  such values in the deploy workflow instead.

- Derive values that depend on the cluster topology in the deploy workflow, not
  in `.env.production`. The database URL, both Redis URLs, the rspamd URL and
  the mail certificate paths are functions of the Service names in `deploy/k8s`,
  and the workflow builds the `relay-cluster-env` Secret from them. Stored in the
  encrypted file they would freeze the topology and go stale on the next
  password rotation.

- Always set `HOSTNAME` explicitly from the `relay-infra` Secret. The image
  entrypoint decrypts `.env.production` without `--overload`, so what the kubelet
  injects wins, and Kubernetes sets `HOSTNAME` to the pod name. relay reads it
  for the platform domain at settings load, so every DNS record it served would
  otherwise be named after a pod. It comes from the Secret, not a literal, so
  the value keeps one source: `.env.production`.

- The entrypoint decrypts the environment; it does not validate it. `--strict`
  stops a container whose environment file is missing, but a key deleted from
  `.env.production` still falls back to Django's defaults (`DATABASE_URL` to
  SQLite, `SECRET_KEY` to the insecure development value).

- Do not add pod anti-affinity on a single node. Nothing can be spread across
  nodes that do not exist, so it is dead weight until the cluster has more than
  one. Add `preferredDuringSchedulingIgnoredDuringExecution` (never
  `requiredDuringScheduling`) as part of the multi-node step.

- Keep `postgres` and `redis-tasks` at one replica. A second independent replica
  is not redundancy for a database or a task queue; it is a divergent dataset.
  Run one `crontask` as well: it elects a single scheduler through a Redis lock,
  so a second replica would wait for the first to stop rather than share the
  work.

- Mount the `caddy-data` claim into the mail servers read-only. It is where
  Caddy writes the certificates they read, and losing it costs a week of
  Let's Encrypt duplicate-certificate budget, not just a restart.

## Provisioning steps

- Every step in `deploy/steps/` must be safe to run twice. Check the real
  resource before changing anything, so a rerun resumes rather than duplicating.
  `deploy/provision.sh` stops at the first step that is not done and depends on
  that.

- A destructive action is an opt-in flag on its step, never something a bare
  `./deploy/provision.sh` can reach. `--reinit` on the server step reinstalls the
  box for that reason, and is run directly.

- Object storage credentials have two spellings, because two readers want
  different names: the `aws` CLI reads `AWS_ACCESS_KEY_ID` while django-storages
  reads `AWS_S3_ACCESS_KEY_ID`, and `.env.production` stores the second. A step
  that shells out to the CLI calls `adopt_stored_s3_credentials` first, so only
  the first provisioning needs them exported.
