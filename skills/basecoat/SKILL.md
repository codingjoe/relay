---
name: basecoat
description: Build frontend UIs with BasecoatUI: a framework-agnostic Tailwind CSS component library compatible with shadcn/ui themes. Reference all 41 components, JS requirements, data-attributes, CDN usage, themes, and Jinja/Nunjucks macros.
---

# BasecoatUI

BasecoatUI (package `basecoat-css`) is a framework-agnostic component library by [Ronan Berder](https://basecoatui.com/) (`hunvreus/basecoat`). It brings the shadcn/ui design philosophy to non-React stacks: pre-styled, accessible HTML components built on Tailwind CSS v4, with a small vanilla-JS runtime for interactive components.

This skill covers `basecoat-css@1.0.2`. Verified by rendering a page with the CDN and screenshotting it.

## 1. Install

### npm + Tailwind v4

```bash
npm install basecoat-css
```

In your CSS entry (Tailwind v4):

```css
@import "tailwindcss";
@import "basecoat-css";
/* default Vega bundle */
/* or @import "basecoat-css/maia"; */
/* named style pack */
```

For interactive components, load the JS:

```html
<script defer="" src="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/js/all.min.js">
</script>
```

Or import from a bundler:

```js
import "basecoat-css/all"; /* all interactive components */
```

### CDN (plain HTML / quick prototype)

```html
<link href="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/basecoat.cdn.min.css" rel="stylesheet"/>
<script defer="" src="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/js/all.min.js">
</script>
```

Named style pack (e.g. `maia`):

```html
<link href="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/basecoat-maia.cdn.min.css" rel="stylesheet"/>
```

## 2. Render a quick preview

Save this as `basecoat-preview.html`, then open it:

```bash
cat > basecoat-preview.html <<'EOF'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Basecoat preview</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/basecoat.cdn.min.css" />
  <script src="https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/js/all.min.js" defer></script>
</head>
<body class="bg-background text-foreground p-8 max-w-3xl mx-auto space-y-8">
  <h1 class="text-3xl font-bold">Basecoat preview</h1>

  <section class="space-y-2">
    <h2 class="text-xl font-semibold">Buttons</h2>
    <div class="flex flex-wrap gap-2">
      <button class="btn">Default</button>
      <button class="btn" data-variant="secondary">Secondary</button>
      <button class="btn" data-variant="outline">Outline</button>
      <button class="btn" data-variant="destructive">Destructive</button>
      <button class="btn" data-variant="ghost">Ghost</button>
      <button class="btn" data-variant="link">Link</button>
    </div>
  </section>

  <section class="space-y-2">
    <h2 class="text-xl font-semibold">Badges</h2>
    <div class="flex flex-wrap gap-2">
      <span class="badge">Default</span>
      <span class="badge" data-variant="secondary">Secondary</span>
      <span class="badge" data-variant="destructive">Destructive</span>
      <span class="badge" data-variant="outline">Outline</span>
    </div>
  </section>

  <section class="space-y-2">
    <h2 class="text-xl font-semibold">Card + form</h2>
    <div class="card">
      <header><h2>Login</h2><p>Enter your email below.</p></header>
      <section>
        <form class="grid gap-4">
          <div class="grid gap-2">
            <label class="label" for="email">Email</label>
            <input class="input" id="email" type="email" placeholder="m@example.com" />
          </div>
          <div class="grid gap-2">
            <label class="label" for="password">Password</label>
            <input class="input" id="password" type="password" />
          </div>
        </form>
      </section>
      <footer><button class="btn w-full">Login</button></footer>
    </div>
  </section>

  <section class="space-y-2">
    <h2 class="text-xl font-semibold">Select (JS)</h2>
    <div id="fruit" class="select w-60" data-placeholder="Pick a fruit">
      <button type="button" id="fruit-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="fruit-listbox" class="w-full">
        <span class="truncate">Pick a fruit</span>
      </button>
      <div data-popover aria-hidden="true">
        <div role="listbox" id="fruit-listbox" aria-labelledby="fruit-trigger">
          <div role="option" data-value="apple">Apple</div>
          <div role="option" data-value="banana">Banana</div>
          <div role="option" data-value="grapes">Grapes</div>
        </div>
      </div>
      <input type="hidden" name="fruit" value="" />
    </div>
  </section>

  <section class="space-y-2">
    <h2 class="text-xl font-semibold">Table</h2>
    <div class="table-container">
      <table class="table">
        <thead><tr><th>Invoice</th><th>Status</th><th class="text-end">Amount</th></tr></thead>
        <tbody>
          <tr><td class="font-medium">INV001</td><td>Paid</td><td class="text-end">$250.00</td></tr>
          <tr><td class="font-medium">INV002</td><td>Pending</td><td class="text-end">$150.00</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</body>
</html>
EOF
python3 -m http.server 8765 --bind 127.0.0.1 &
chromium-cli screenshot http://127.0.0.1:8765/basecoat-preview.html
```

## 3. Anatomy of a Basecoat component

Most components follow this shape:

1. **Root class**: e.g. `btn`, `card`, `table`. Apply it to the root element.
1. **Semantic structure**: many components use child `<header>`, `<section>`, `<footer>` (cards, dialogs, popovers).
1. **Variants / sizes / state** via `data-*` attributes: e.g. `data-variant="outline"`, `data-size="sm"`.
1. **ARIA roles**: the docs rely on native semantics plus explicit roles (`role="tablist"`, `role="menu"`, `role="listbox"`, etc.).
1. **Tailwind utilities**: Basecoat uses your Tailwind configuration, so utilities like `w-full`, `flex`, `gap-2` continue to work.

Common variants: `default`, `secondary`, `destructive`, `outline`, `ghost`, `link`.
Common sizes: `default`, `sm`, `lg`, `icon`, `icon-sm`.
Not every component supports all of these; check the component page for its specific set.

## 4. Component catalog (41 components)

| Component                                                           | Root class                                                 | Needs JS                                                                          | Key `data-*` attributes                                                                                                                                                                     | Minimal example                                                                                                                                                              |
| ------------------------------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Accordion](https://basecoatui.com/components/accordion/)           | `accordion`                                                | ✅ `accordion.min.js`                                                             | `data-multiple`                                                                                                                                                                             | `<section class="accordion"><details><summary>Q1</summary><section>A1</section></details></section>`                                                                         |
| [Alert Dialog](https://basecoatui.com/components/alert-dialog/)     | `alert-dialog` on `<dialog>`                               | ❌ (native `<dialog>`)                                                            | `data-size`, `data-variant`                                                                                                                                                                 | `<dialog class="alert-dialog"><div><header><h2>Title</h2><p>Description</p></header><footer><button class="btn">OK</button></footer></div></dialog>`                         |
| [Alert](https://basecoatui.com/components/alert/)                   | `alert`                                                    | ❌                                                                                | `data-size`, `data-variant`                                                                                                                                                                 | `<div class="alert" data-variant="destructive"><h2>Error</h2><section>Message</section></div>`                                                                               |
| [Avatar](https://basecoatui.com/components/avatar/)                 | `avatar`, `avatar-group`                                   | ❌                                                                                | `data-size`, `data-variant`, `data-popover`, `data-count`                                                                                                                                   | `<span class="avatar"><img src="u.png" alt="User" /><span>CN</span></span>`                                                                                                  |
| [Badge](https://basecoatui.com/components/badge/)                   | `badge`                                                    | ❌                                                                                | `data-variant`, `data-icon`                                                                                                                                                                 | `<span class="badge" data-variant="secondary">New</span>`                                                                                                                    |
| [Breadcrumb](https://basecoatui.com/components/breadcrumb/)         | `breadcrumb`                                               | ❌                                                                                | `data-size`, `data-variant`, `data-popover`, `data-rtl-flip`                                                                                                                                | `<nav class="breadcrumb" aria-label="Breadcrumb"><ol><li><a href="#">Home</a></li><li aria-hidden="true">/</li><li><span aria-current="page">Current</span></li></ol></nav>` |
| [Button Group](https://basecoatui.com/components/button-group/)     | `button-group`                                             | ❌                                                                                | `data-orientation`, `data-size`, `data-variant`, `data-align`, `data-label`, `data-name`, `data-value`, `data-popover`                                                                      | `<div role="group" class="button-group"><button class="btn" data-variant="outline">A</button><button class="btn" data-variant="outline">B</button></div>`                    |
| [Button](https://basecoatui.com/components/button/)                 | `btn`                                                      | ❌                                                                                | `data-variant`, `data-size`, `data-icon`, `data-popover`, `data-align`                                                                                                                      | `<button class="btn" data-variant="outline" data-size="sm">Save</button>`                                                                                                    |
| [Card](https://basecoatui.com/components/card/)                     | `card`                                                     | ❌                                                                                | `data-size`, `data-variant`                                                                                                                                                                 | `<div class="card"><header><h2>Title</h2></header><section>Body</section><footer>Footer</footer></div>`                                                                      |
| [Chart](https://basecoatui.com/components/chart/)                   | `<canvas>`                                                 | ✅ `basecoat.min.js` + `chart.umd.min.js` + `chart.min.js` (Chart.js not bundled) | :                                                                                                                                                                                           | See docs; not included in `all.min.js`.                                                                                                                                      |
| [Checkbox](https://basecoatui.com/components/checkbox/)             | `input` (on `<input type="checkbox">`)                     | ❌                                                                                | `data-orientation`, `data-variant`, `data-disabled`, `data-invalid`, `data-slot="checkbox-table"`                                                                                           | `<div role="group" class="field" data-orientation="horizontal"><input type="checkbox" id="c1" class="input" /><label for="c1">Accept</label></div>`                          |
| [Combobox](https://basecoatui.com/components/combobox/)             | `combobox`                                                 | ✅ `combobox.min.js`                                                              | `data-clear`, `data-auto-highlight`, `data-filter`, `data-format`, `data-invalid`, `data-label`, `data-placeholder`, `data-popover`, `data-side`, `data-size`, `data-value`, `data-variant` | See full example below in JS components.                                                                                                                                     |
| [Command](https://basecoatui.com/components/command/)               | `command`                                                  | ✅ `command.min.js`                                                               | `data-empty`, `data-filter`, `data-force`, `data-keep-command-open`, `data-keywords`, `data-shortcut`, `data-checked`, `data-disabled`, `data-indicator`, `data-variant`                    | See full example below in JS components.                                                                                                                                     |
| [Dialog](https://basecoatui.com/components/dialog/)                 | `dialog` on `<dialog>`                                     | ❌ (native `<dialog>`)                                                            | `data-size`, `data-variant`                                                                                                                                                                 | `<dialog class="dialog"><div><header><h2>Edit</h2></header><section>Form</section><footer><button class="btn">Save</button></footer></div></dialog>`                         |
| [Drawer](https://basecoatui.com/components/drawer/)                 | `drawer` on `<dialog>`                                     | ✅ `drawer.min.js`                                                                | `data-side`, `data-size`, `data-variant`, `data-drawer-initialized`                                                                                                                         | `<dialog class="drawer"><article><header><h2>Title</h2></header><section>Body</section><footer><button class="btn">OK</button></footer></article></dialog>`                  |
| [Dropdown Menu](https://basecoatui.com/components/dropdown-menu/)   | `dropdown-menu`                                            | ✅ `dropdown-menu.min.js`                                                         | `data-align`, `data-side`, `data-size`, `data-variant`, `data-popover`, `data-indicator`                                                                                                    | See full example below in JS components.                                                                                                                                     |
| [Empty](https://basecoatui.com/components/empty/)                   | `empty`                                                    | ❌                                                                                | `data-align`, `data-icon`, `data-size`, `data-variant`                                                                                                                                      | `<section class="empty"><header><figure></figure><h3>No items</h3><p>Add one to get started.</p></header><footer><button class="btn">Create</button></footer></section>`     |
| [Field](https://basecoatui.com/components/field/)                   | `field`                                                    | ❌                                                                                | `data-orientation`, `data-variant`, `data-disabled`, `data-invalid`                                                                                                                         | `<div role="group" class="field"><label for="x">Name</label><input id="x" class="input" /></div>`                                                                            |
| [Input Group](https://basecoatui.com/components/input-group/)       | `input-group`                                              | ❌                                                                                | `data-align`, `data-control`, `data-orientation`, `data-popover`, `data-size`, `data-variant`                                                                                               | `<div class="input-group"><span>$</span><input class="input" type="text" /></div>`                                                                                           |
| [Input](https://basecoatui.com/components/input/)                   | `input`                                                    | ❌                                                                                | `data-size`, `data-variant`                                                                                                                                                                 | `<input class="input" type="email" placeholder="Email" />`                                                                                                                   |
| [Item](https://basecoatui.com/components/item/)                     | `item`                                                     | ❌                                                                                | `data-size`, `data-variant`, `data-align`, `data-icon`, `data-popover`                                                                                                                      | `<article class="item"><section><h3>Title</h3><p>Desc</p></section><aside><button class="btn" data-size="sm">Action</button></aside></article>`                              |
| [Kbd](https://basecoatui.com/components/kbd/)                       | `kbd`                                                      | ❌                                                                                | `data-variant`, `data-size`, `data-align`, `data-icon`                                                                                                                                      | `<kbd>⌘K</kbd>`                                                                                                                                                              |
| [Label](https://basecoatui.com/components/label/)                   | `label`                                                    | ❌                                                                                | :                                                                                                                                                                                           | `<label class="label" for="id">Email</label>`                                                                                                                                |
| [Native Select](https://basecoatui.com/components/native-select/)   | `select` on `<select>`                                     | ❌                                                                                | `data-size`, `data-invalid`                                                                                                                                                                 | `<select class="select w-full"><option>One</option><option>Two</option></select>`                                                                                            |
| [Pagination](https://basecoatui.com/components/pagination/)         | uses `btn`                                                 | ❌                                                                                | `data-size`, `data-variant`                                                                                                                                                                 | `<nav aria-label="pagination"><ul class="flex gap-1"><li><a class="btn" data-size="icon" href="#">1</a></li></ul></nav>`                                                     |
| [Popover](https://basecoatui.com/components/popover/)               | `popover`                                                  | ✅ `popover.min.js`                                                               | `data-align`, `data-side`, `data-variant`, `data-popover`                                                                                                                                   | See full example below in JS components.                                                                                                                                     |
| [Progress](https://basecoatui.com/components/progress/)             | `progress`                                                 | ❌                                                                                | :                                                                                                                                                                                           | `<div class="progress" role="progressbar"><span style="width: 66%"></span></div>`                                                                                            |
| [Radio Group](https://basecoatui.com/components/radio-group/)       | `input` (on `<input type="radio">`)                        | ❌                                                                                | `data-orientation`, `data-variant`, `data-disabled`, `data-invalid`, `data-slot="radio-group"`                                                                                              | `<div role="radiogroup"><div class="flex gap-3"><input type="radio" id="r1" name="g" class="input" /><label for="r1">Yes</label></div></div>`                                |
| [Scroll Area](https://basecoatui.com/components/scroll-area/)       | `scrollbar`                                                | ❌                                                                                | :                                                                                                                                                                                           | `<div class="scrollbar h-48 overflow-y-auto">Long content…</div>`                                                                                                            |
| [Select](https://basecoatui.com/components/select/)                 | `select` on `<div>`                                        | ✅ `select.min.js`                                                                | `data-align`, `data-close-on-select`, `data-format`, `data-invalid`, `data-label`, `data-placeholder`, `data-popover`, `data-side`, `data-size`, `data-value`, `data-variant`               | See full example below in JS components.                                                                                                                                     |
| [Sidebar](https://basecoatui.com/components/sidebar/)               | `sidebar`                                                  | ✅ `sidebar.min.js`                                                               | `data-side`, `data-size`, `data-variant`, `data-breakpoint`, `data-active`, `data-initial-open`, `data-initial-mobile-open`, `data-keep-mobile-sidebar-open`                                | See docs / use `sidebar()` macro.                                                                                                                                            |
| [Skeleton](https://basecoatui.com/components/skeleton/)             | `skeleton`                                                 | ❌                                                                                | :                                                                                                                                                                                           | `<div class="skeleton h-4 w-48 rounded"></div>`                                                                                                                              |
| [Slider](https://basecoatui.com/components/slider/)                 | `input` (on `<input type="range">`)                        | ✅ `range.min.js`                                                                 | :                                                                                                                                                                                           | `<input type="range" class="input w-full" min="0" max="100" value="50" />`                                                                                                   |
| [Spinner](https://basecoatui.com/components/spinner/)               | none (pure Tailwind)                                       | ❌                                                                                | :                                                                                                                                                                                           | **Not a component.** Use a Lucide loader icon with `animate-spin`: `<svg class="animate-spin lucide lucide-loader-circle" … />`                                              |
| [Switch](https://basecoatui.com/components/switch/)                 | `input` (on `<input type="checkbox" role="switch">`)       | ❌                                                                                | `data-size`, `data-variant`, `data-orientation`, `data-disabled`, `data-invalid`                                                                                                            | `<div role="group" class="field" data-orientation="horizontal"><input type="checkbox" id="s1" role="switch" class="input" /><label for="s1">Airplane mode</label></div>`     |
| [Table](https://basecoatui.com/components/table/)                   | `table` on `<table>`                                       | ❌                                                                                | `data-size`, `data-variant`                                                                                                                                                                 | `<div class="table-container"><table class="table">…</table></div>`                                                                                                          |
| [Tabs](https://basecoatui.com/components/tabs/)                     | `tabs`                                                     | ✅ `tabs.min.js`                                                                  | `data-variant`                                                                                                                                                                              | See full example below in JS components.                                                                                                                                     |
| [Textarea](https://basecoatui.com/components/textarea/)             | `textarea`                                                 | ❌                                                                                | :                                                                                                                                                                                           | `<textarea class="textarea" placeholder="Type…"></textarea>`                                                                                                                 |
| [Theme Switcher](https://basecoatui.com/components/theme-switcher/) | `theme-switcher` (or use `window.basecoat.theme.toggle()`) | ✅ `basecoat.min.js` (part of `all.min.js`)                                       | `data-side`, `data-size`, `data-tooltip`, `data-variant`                                                                                                                                    | `<button class="btn" data-size="icon" data-tooltip="Toggle dark mode" onclick="window.basecoat.theme.toggle()">🌙</button>`                                                  |
| [Toast](https://basecoatui.com/components/toast/)                   | `toast`                                                    | ✅ `toast.min.js`                                                                 | `data-align`, `data-category`, `data-duration`, `data-toast-action`, `data-variant`                                                                                                         | See docs / use `toast()`/`toaster()` macros.                                                                                                                                 |
| [Tooltip](https://basecoatui.com/components/tooltip/)               | any element                                                | ❌                                                                                | `data-tooltip`, `data-side`, `data-align`, `data-size`                                                                                                                                      | `<button class="btn" data-tooltip="Add to library">Hover</button>`                                                                                                           |

## 5. JavaScript components (interactive)

Only 13 of the 41 components need the Basecoat runtime. Load the full bundle (`all.min.js`) or the runtime + per-component script.

| Component      | Required JS (runtime + component)                       | Notes                                                                     |
| -------------- | ------------------------------------------------------- | ------------------------------------------------------------------------- |
| Accordion      | `basecoat.min.js` + `accordion.min.js`                  | Native `<details>` enhanced. `data-multiple` allows multiple open panels. |
| Combobox       | `basecoat.min.js` + `combobox.min.js`                   | Searchable dropdown with `role="combobox"`.                               |
| Command        | `basecoat.min.js` + `command.min.js`                    | Command palette / filterable menu.                                        |
| Drawer         | `basecoat.min.js` + `drawer.min.js`                     | Slides out from `data-side` (`left`/`right`/`top`/`bottom`).              |
| Dropdown Menu  | `basecoat.min.js` + `dropdown-menu.min.js`              |                                                                           |
| Popover        | `basecoat.min.js` + `popover.min.js`                    |                                                                           |
| Select         | `basecoat.min.js` + `select.min.js`                     | Custom-styled, accessible dropdown.                                       |
| Sidebar        | `basecoat.min.js` + `sidebar.min.js`                    | Collapsible layout sidebar.                                               |
| Slider         | `basecoat.min.js` + `range.min.js`                      | Note: file is named `range.min.js`, not `slider.min.js`.                  |
| Tabs           | `basecoat.min.js` + `tabs.min.js`                       |                                                                           |
| Theme Switcher | `basecoat.min.js` (in `all.min.js`)                     | Exposes `window.basecoat.theme.toggle()`.                                 |
| Toast          | `basecoat.min.js` + `toast.min.js`                      | Usually rendered server-side via HTMX or macro.                           |
| Chart          | `basecoat.min.js` + `chart.min.js` + `chart.umd.min.js` | **Not** in `all.min.js`; Chart.js is a separate peer dependency.          |

### Select example

```html
<div class="select w-60" data-placeholder="Theme" id="theme">
 <button aria-controls="theme-listbox" aria-expanded="false" aria-haspopup="listbox" class="w-full" id="theme-trigger" type="button">
  <span class="truncate">
   Theme
  </span>
 </button>
 <div aria-hidden="true" data-popover="">
  <div aria-labelledby="theme-trigger" id="theme-listbox" role="listbox">
   <div data-value="light" role="option">
    Light
   </div>
   <div data-value="dark" role="option">
    Dark
   </div>
  </div>
 </div>
 <input name="theme" type="hidden" value=""/>
</div>
```

### Dropdown Menu example

```html
<div class="dropdown-menu" id="menu">
 <button aria-controls="menu-menu" aria-expanded="false" aria-haspopup="menu" class="btn" data-variant="outline" id="menu-trigger" type="button">
  Open
 </button>
 <div aria-hidden="true" data-align="end" data-popover="" id="menu-popover">
  <div aria-labelledby="menu-trigger" id="menu-menu" role="menu">
   <div role="group">
    <div role="heading">
     My Account
    </div>
    <div role="menuitem">
     <span>
      Profile
     </span>
     <kbd>
      ⇧⌘P
     </kbd>
    </div>
    <div role="menuitem">
     <span>
      Billing
     </span>
     <kbd>
      ⌘B
     </kbd>
    </div>
   </div>
   <hr role="separator"/>
   <div role="group">
    <div role="menuitem">
     Log out
    </div>
   </div>
  </div>
 </div>
</div>
```

### Tabs example

```html
<div class="tabs" id="tabs">
 <nav aria-orientation="horizontal" role="tablist">
  <button aria-controls="tabs-p1" aria-selected="true" id="tabs-1" role="tab" tabindex="0" type="button">
   Account
  </button>
  <button aria-controls="tabs-p2" aria-selected="false" id="tabs-2" role="tab" tabindex="-1" type="button">
   Password
  </button>
 </nav>
 <div aria-labelledby="tabs-1" aria-selected="true" id="tabs-p1" role="tabpanel" tabindex="-1">
  Account content
 </div>
 <div aria-labelledby="tabs-2" aria-selected="false" hidden="" id="tabs-p2" role="tabpanel" tabindex="-1">
  Password content
 </div>
</div>
```

### Combobox example

```html
<div class="combobox" id="combo">
 <input aria-autocomplete="list" aria-controls="combo-listbox" aria-expanded="false" autocomplete="off" placeholder="Select…" role="combobox" type="text"/>
 <div aria-hidden="true" data-popover="">
  <div data-empty="No items found." id="combo-listbox" role="listbox">
   <div data-value="a" role="option">
    A
   </div>
   <div data-value="b" role="option">
    B
   </div>
  </div>
 </div>
 <input name="combo" type="hidden" value=""/>
</div>
```

### Command example

```html
<div aria-label="Command menu" class="command border">
 <header>
  <input aria-autocomplete="list" aria-controls="cmd-menu" aria-expanded="true" autocomplete="off" placeholder="Type a command…" role="combobox" type="text"/>
 </header>
 <div data-empty="No results found." id="cmd-menu" role="menu">
  <div role="group">
   <span role="heading">
    Suggestions
   </span>
   <div data-filter="Calendar" data-keywords="date event" role="menuitem">
    Calendar
   </div>
  </div>
 </div>
</div>
```

### Dialog / Drawer (native `<dialog>`)

`Dialog`, `Alert Dialog`, and `Drawer` do **not** need Basecoat JS. Use the native HTML `<dialog>` API:

```html
<button class="btn" data-variant="outline" onclick="document.getElementById('dlg').showModal()">
 Open
</button>
<dialog class="dialog" id="dlg" onclick="if (event.target === this) this.close()">
 <div class="sm:max-w-sm">
  <header>
   <h2>
    Edit profile
   </h2>
  </header>
  <section>
   Make changes here.
  </section>
  <footer>
   <button class="btn" data-variant="outline" onclick="this.closest('dialog').close()">
    Cancel
   </button>
   <button class="btn" onclick="this.closest('dialog').close()">
    Save
   </button>
  </footer>
 </div>
</dialog>
```

For `drawer`, use `<dialog class="drawer">` with an `<article>` child and `data-side`.

## 6. Jinja / Nunjucks macros

Basecoat ships 11 optional macros for server-rendered apps. Import them from the `basecoat-css` package templates path (or copy the templates into your project). These are especially useful for Select, Combobox, Dropdown Menu, Sidebar, Tabs, and Toast.

| Macro              | Arguments                                                                                                                                                                                        | Covers                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| `combobox()`       | `id`, `selected`, `name`, `multiple`, `placeholder`, `close_on_select`, `clear`, `auto_highlight`, `format`, `main_attrs`, `input_attrs`, `popover_attrs`, `listbox_attrs`, `hidden_input_attrs` | Combobox                    |
| `command()`        | `id`, `items`, `placeholder`, `empty_text`, `main_attrs`, `input_attrs`, `menu_attrs`                                                                                                            | Command palette             |
| `command_dialog()` | `id`, `items`, `placeholder`, `empty_text`, `dialog_attrs`, `input_attrs`, `menu_attrs`, `open`                                                                                                  | Command palette in a dialog |
| `dialog()`         | `id`, `trigger`, `title`, `description`, `footer`, `dialog_attrs`, `trigger_attrs`, `header_attrs`, `body_attrs`, `footer_attrs`, `open`, `close_button`, `close_on_overlay_click`               | Dialog                      |
| `dropdown_menu()`  | `trigger`, `id`, `items`, `main_attrs`, `trigger_attrs`, `popover_attrs`, `menu_attrs`                                                                                                           | Dropdown Menu               |
| `popover()`        | `trigger`, `id`, `main_attrs`, `trigger_attrs`, `popover_attrs`                                                                                                                                  | Popover                     |
| `select()`         | `id`, `selected`, `name`, `items`, `multiple`, `placeholder`, `close_on_select`, `format`, `main_attrs`, `trigger_attrs`, `popover_attrs`, `listbox_attrs`, `input_attrs`                        | Select                      |
| `sidebar()`        | `id`, `label`, `open`, `side`, `header`, `footer`, `menu`, `main_attrs`, `header_attrs`, `content_attrs`, `footer_attrs`                                                                         | Sidebar                     |
| `tabs()`           | `id`, `tabsets`, `main_attrs`, `tablist_attrs`, `default_tab_index`                                                                                                                              | Tabs                        |
| `toast()`          | `category`, `title`, `description`, `duration`, `icon`, `action`, `cancel`, `attrs`                                                                                                              | Individual toast            |
| `toaster()`        | `id`, `toasts`, `attrs`                                                                                                                                                                          | Toast container             |

See `site/src/docs/templates.mdx` in the `hunvreus/basecoat` repo for full signatures and examples.

## 7. Themes / style packs

Basecoat separates component structure from visual style. You can use:

- A full bundle: `@import "basecoat-css";` (default Vega)
- A named style pack: `@import "basecoat-css/maia";`
- Base only + your own style: `@import "basecoat-css/base.css";` then `@import "./style-acme.css";`
- Base + one component + one style: `@import "basecoat-css/components/button.css"; @import "basecoat-css/styles/vega.css";`

Built-in style packs: `vega`, `nova`, `maia`, `lyra`, `mira`, `luma`, `sera`, `rhea`.

To create a custom theme, write CSS variables in the same structure as `src/css/styles/<pack>.css` in the Basecoat repo.

## 8. Gotchas

- **“Needs JS” means Basecoat JS.** Many components are purely CSS (`btn`, `card`, `input`, `table`, `alert`, `badge`, `tooltip`). Do not import JS for them. The 13 JS components are listed in §5.
- **Native Select vs. custom Select.** Both use the class `select`, but Native Select is `<select class="select">` (no JS), while Select is `<div class="select">` (requires JS).
- **Checkbox / Radio / Switch all use `class="input"`.** Do not invent `class="checkbox"`. Style variants and state come from `data-*` attributes on the surrounding `field` or from the native element.
- **Dialog/Alert Dialog/Drawer use native `<dialog>`.** Open them with `.showModal()` and close with `.close()`. No Basecoat JS runtime is required, though Drawer needs `drawer.min.js` for extra behavior.
- **Slider JS file is `range.min.js`.** It is named after the range input, not the component.
- **Chart is not in `all.min.js`.** It needs Chart.js (`chart.umd.min.js`) plus Basecoat's `chart.min.js`.
- **Spinner is not a component.** It is a plain Lucide `lucide-loader-circle` icon with `animate-spin`. No Basecoat CSS file exists.
- **Scroll Area uses `scrollbar`, not `scroll-area`.** Apply `class="scrollbar"` to the scrollable container.
- **Load Basecoat CSS after Tailwind.** The docs explicitly say: load Basecoat after any stylesheet containing Tailwind base/preflight.
- **SVG icons are not provided.** The docs use Lucide icons. Use `<svg class="lucide lucide-icon-name">` or your own icon set.
- **No test suite.** Use pre-commit/ruff for quality; do not write Django-style tests for the markup.

## 9. External links

- Homepage: https://basecoatui.com/
- GitHub: https://github.com/hunvreus/basecoat
- npm: https://www.npmjs.com/package/basecoat-css
- Intro: https://basecoatui.com/introduction/
- Install: https://basecoatui.com/installation/
- Components index: https://basecoatui.com/components/
