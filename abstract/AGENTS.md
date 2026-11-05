# Shared Model and Python Conventions

Apply these rules to every app.

## Primary Keys

- Prefer `BigAutoField` for most models. Use title slugs in URLs, not UUIDs.
- Use `db_default` with a PostgreSQL function such as `UuidV7()`, plus the
  Python `default=uuid.uuid7`.

## Model Fields

- All fields have `verbose_name` and `help_text`, except FK and PK.
- Use `db_defaults` where a database default is appropriate.
- Index fields used for ordering. Every field in `Meta.ordering` needs an
  index.
- Drop `class Meta` if it only inherits.
- Use `TextField` unless you need `max_length` validation. PostgreSQL has no
  performance difference. Choice fields use `TextField` with `choices=`.
  `CharField(max_length=N)` is for fixed standards such as `EmailField`.

## Model.save()

- Always pass explicit `update_fields=`.
- Use `force_insert=True` when creating.

## Migrations

- Never drop a column or table in the same release that stops using it. A
  failed deploy keeps migrations applied, so the previous image must still
  run. Ship the code first, drop the schema later.

## Model methods

- A model with `__str__` also defines `__repr__` or inherits one.
  `abstract.W005` enforces this.

## Functions

- Use descriptive names. Do not write one-liner wrappers around a single
  expression.
- Use generators for lazy sequences, such as walking relations.
- Do not annotate overridden methods. The base class defines the contract.

## Comments

- Comment only unexpected or hard-to-read code. Never restate the line.
- For configuration, link the docs and keep only the fact the docs lack.
- Keep comments to one line. Prefer a trailing annotation for an unexpected
  literal.

## Docstrings

- Use Google-style Markdown docstrings (Napoleon).
- Start with a verb describing external behavior. Keep simple functions to
  one sentence. Never repeat the function name or describe implementation.
- Use bullet lists only for 3+ non-obvious parameters. Do not document
  inherited methods.

## Control Flow

- Prefer `match`/`case` over if-chains.
- Use `get_object_or_404()` in views.

## Imports

- Do not import per-property. Import the module directly.

## Naming

- Use names that cover ingress and egress, such as `Transmission`, not
  `Delivery`.
- Avoid abbreviations. Write `nameserver`, not `ns`. This covers fields,
  verbose names, and help text.
- Do not wrap protocol terms in `gettext`.

## Admin

- List every editable FK and M2M field in `autocomplete_fields`. The related
  admin needs `search_fields` and its own admin. `abstract.W004` warns about
  a missing autocomplete.

## Views & Queries

- Publicly cacheable views (`public: True`) render `request.public_cache`:
  no user menu, toasts, or org switcher. They carry no `Vary: Cookie` and no
  queries.
- Forms, redirects, and template views answer `no-store`.
- Do not add context processors that provide querysets. Template chrome data
  comes from the view's mixin.
- Fetch a list once. Derive counts, flags, and related objects from it.
- `TimeStamped` models default to `models.FETCH_PEERS`. Do not call
  `.fetch_mode()` in views.
- `TimeStamped.save()` persists `modified_at` on partial saves.
  `QuerySet.update()` must pass `modified_at=timezone.now()`.

## Multi-table inheritance

- When siblings share most columns, promote them to a concrete parent.
  Per-kind fields stay on the children.
- When they share only a few columns, prefer an abstract base with concrete
  per-scenario models. Put shared behavior on the base.
- Indexes on shared columns live on the parent. Per-kind indexes stay on the
  child.
- A `content_type` FK records the subclass. The base `Message.save()` sets it.
