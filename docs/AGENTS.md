# Documentation Instructions

Apply these rules to `docs`, `know_how`, `alternative_to`, and `legal`.

## Markdown docs apps

- Serve each area from one app with a `docs/` folder. Extend
  `MarkdownArticleMixin` from `abstract.views`.
- Keep slugs unique across docs apps. The template loader resolves
  `<slug>.md` against every TEMPLATES DIRS entry.
- Write relay-specific user docs in `docs/docs`.
