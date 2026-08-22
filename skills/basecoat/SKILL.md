---
name: basecoat
description: Build frontend UIs with BasecoatUI. A framework-agnostic Tailwind CSS component library compatible with shadcn/ui themes. Use live docs, not stale examples in this skill.
---

# BasecoatUI

BasecoatUI (`basecoat-css`) is a framework-agnostic Tailwind CSS v4 component library by Ronan Berder (`hunvreus/basecoat`). It works like shadcn/ui for non-React stacks: semantic HTML classes + a small vanilla-JS runtime for interactive components.

**Do not copy examples from this file.** They age. Fetch the live docs instead.

## How to fetch docs

Basecoat publishes a machine-readable page index and per-page markdown exports.

1. Get the page index: `curl https://basecoatui.com/llms.txt`.
1. Find the slug for the component or guide you need.
1. Build the markdown URL: replace a trailing `/` with `.md` or append `.md` if there is no trailing slash. Examples:
   - `https://basecoatui.com/components/select/` becomes `https://basecoatui.com/components/select.md`
   - `https://basecoatui.com/introduction/` becomes `https://basecoatui.com/introduction.md`
   - `https://basecoatui.com/templates/` becomes `https://basecoatui.com/templates.md`
1. Fetch that `.md` page and use it as the source of truth for markup, variants, `data-*` attributes, ARIA roles, and JS requirements.
1. For the GitHub repo readme, run `gh repo view hunvreus/basecoat --readme`.

## Core conventions

Use these facts when reading Basecoat docs.

### Installation

- npm: `npm install basecoat-css`. Import in CSS with `@import "basecoat-css";`.
- CDN stylesheet: `https://cdn.jsdelivr.net/npm/basecoat-css@{version}/dist/basecoat.cdn.min.css`. Named style packs use files like `basecoat-maia.cdn.min.css`.
- CSS imports must come after Tailwind base/preflight.
- Interactive components need `dist/js/all.min.js`, or `basecoat.min.js` plus a per-component script.

### Anatomy

- Root class defines the component: `btn`, `card`, `table`, `select`, etc.
- Structural components often use `<header>`, `<section>`, and `<footer>` children.
- Variants, sizes, and state are controlled by `data-*` attributes such as `data-variant` and `data-size`, not by extra classes.
- Common variants across many components: `default`, `secondary`, `destructive`, `outline`, `ghost`, `link`.
- Tailwind utilities still work alongside Basecoat classes.

### JavaScript components

Only some components need the Basecoat JS runtime. Confirm per component by fetching its `.md` page.

Key gotchas:

- `dialog`, `alert-dialog`, and `drawer` use the native `<dialog>` element. Open with `.showModal()`, close with `.close()`. Drawer still needs `drawer.min.js`.
- Slider is powered by `range.min.js`, not `slider.min.js`.
- Chart is not in `all.min.js`; it needs `chart.min.js` plus Chart.js (`chart.umd.min.js`).
- `select` is a custom `<div>`; `native-select` is a real `<select>`. Both use `class="select"`.
- Checkbox, radio, and switch all use `class="input"`.
- Spinner is not a Basecoat class; use a Lucide loader icon with `animate-spin`.
- Scroll Area uses `class="scrollbar"` on the scrollable container.

### Macros

Basecoat ships Jinja/Nunjucks macros for server-rendered apps. Fetch `https://basecoatui.com/templates.md` when a component page says to use a macro.

### Themes

- The default bundle is the Vega style pack. Import named packs like `@import "basecoat-css/maia";`.
- Basecoat uses shadcn/ui-compatible CSS variables (`--background`, `--primary`, etc.). Define them in `theme.css` after the Basecoat import. Generate them with TweakCN or another shadcn/ui theme generator.

## External links

- Home: `https://basecoatui.com/`
- LLMs index: `https://basecoatui.com/llms.txt`
- GitHub: `https://github.com/hunvreus/basecoat`
- npm: `https://www.npmjs.com/package/basecoat-css`
