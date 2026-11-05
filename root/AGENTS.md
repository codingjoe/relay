# UI Instructions

Apply these rules to every template and shared browser module.

## Templates & UI

- Use [basecoat-css](https://basecoatui.com/) (maia style). Do not use pico.css
  or another CSS framework.
- Use template inheritance. Define the shell in `root/templates/base.html`.
  Pages override `{% block title %}` and `{% block content %}`.
- Prefer basecoat components over custom CSS or JS:
  - Buttons: `btn` with `data-variant` and `data-size`. Use `secondary` for
    most non-primary buttons. Reserve `outline` for `item` elements. Use
    `destructive` for delete actions.
  - Cards: `article.card`. Never nest cards.
  - Tables in cards: `article.card.gap-0.p-0.overflow-hidden` with an inner
    padded header and a direct `.table-container`.
  - Tables: `div.table-container > table.table`.
  - Dialogs: `dialog.dialog` with `header`, `section`, and `footer`. Open with
    `.showModal()`, close with `.close()`.
  - Form controls: `input.input`, `select.select.w-full`, `textarea.textarea`.
    Wrap forms in `fieldset.fieldset` and fields in `div.field` with a native
    label. Do not nest inputs in labels or use `span.label`.
  - Autocomplete: use the matching token for member data (`email`, `name`,
    `url`, `tel`, `new-password`, `one-time-code`). Use `off` for search,
    filters, and other people's data.
  - Dropdowns: `div.dropdown-menu` with a trigger button.
  - Avatars: `span.avatar` with `data-size`.
  - Badges: `span.badge` with `data-size` and `data-variant`.
  - Items: `a.item` or `article.item` inside `div.item-group` for clickable
    list rows.
  - Brand: write `relay` in lowercase. Do not translate it or apply casing
    filters.
- Icons use Tabler. Sizes use the
  Tailwind scale (`3`=12px, `3.5`=14px, `4`=16px, `5`=20px, `6`=24px,
  `8`=32px). Use semantic color classes.
- CSS uses PostCSS and wireit. The entry is `src/css/app.css`. Put new rules
  in the matching partial. Run `pnpm run build` to compile to
  `root/static/css/app.css` (gitignored). Run `pnpm run dev` to watch.
  Custom CSS is for layout glue only. Prefer basecoat and Tailwind.
- Form widgets are overridden in
  `abstract/templates/django/forms/widgets/`. Keep the basecoat classes and
  `widget.attrs`. Prefer `{{ form }}` and `{{ form.field }}`.
- Sidebar and main-nav links use `{% url ... as var %}` and
  `request.path == var` for `aria-current="page"`. Do not use substring
  checks. Hide main-nav links when no org is selected.
- Breadcrumbs use `BreadcrumbViewMixin` from `abstract.views`. Set `title` and
  `parent`. Override `get_title` and `get_url` when needed.
- Tailwind preflight resets `a { color: inherit }`. Add `class="link"` to
  entity anchors.
- Code samples live in `root/templates/snippets/` and are included with
  `{% filter force_escape %}{% include ... %}{% endfilter %}`.
- A form that needs a module puts `django_esm.forms.ESM` in its `Media`.
- `pnpm run build` vendors `dependencies` into `staticfiles/esm`. List
  first-party package importers in the `imports` map of `package.json`.
  `esimport --treeshake` starts from those entries.
