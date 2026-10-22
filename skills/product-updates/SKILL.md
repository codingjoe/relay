---
name: product-updates
description: Create relay's monthly product update as a station log, a log of a subspace relay station in the spirit of Deep Space Nine. Use this skill whenever the user asks for product updates, release notes, a changelog, a newsletter, a monthly recap, or a summary of what shipped. The output is a Markdown post in product/updates/ with user-facing copy and focused 1280x640 screenshots. Trigger this even when the user only says "write the newsletter", "what changed this month", or "turn these commits into an update for users".
---

# Product updates

Turn the last month of relay changes into a user-facing station log. The
report ships as a Markdown file in `product/updates/` and doubles as the
newsletter and the website post. Name the file after the month, for example
`product/updates/2026-10.md`, and use the publication date in the frontmatter.

## Audience

Write for relay users. They are developers sending and receiving mail. They
care about what they can now do, see, or trust. They do not care about
dependency bumps, CI, deploy plumbing, or internal refactors unless the change
alters their behavior.

Use `PRODUCT.md` for positioning and `docs/docs/` for the exact behavior. Read
every earlier file in `product/updates/` before you write. Match the voice,
and never repeat a hook, an opening line, a section title, or a metaphor they
already used.

## Collect the month

1. List commits from the window. Use the last 30 days by default, or the
   calendar month the user names.

   ```shell
   git log --since="30 days ago" --pretty=format:"%h %ad %s" --date=short --no-merges
   ```

2. Keep the changes a user can feel. A feature, a flow, a status, a limit, a
   reliability fix, a security fix, or a developer-experience change. Drop
   version bumps, test-only work, refactors, and infrastructure.

3. Sort features from improvements. Ask what the reader can do now that they
   could not do before. A new screen, control, or capability is a feature. A
   layout, flow, copy, reliability, or delivery change is an improvement,
   even when it prevents lost mail. A change the reader only meets in a
   transcript, a status detail, or a background job is an internal
   optimization. Lead with features and give each one a stardate entry. Put
   an improvement in the supplemental log, unless users asked for it loudly.
   When in doubt, ask the user whether the change was requested. Leave an
   internal optimization out entirely. The supplemental log is not a
   changelog either, and the main log records new capability.

4. Read the merge or pull request description for the "why". `git show <sha>`
   includes the PR body. `gh pr view <number>` works too. Prefer the user
   outcome over the implementation detail. A PR body that opens with "I
   want" is usually a feature. One that opens with "today the flow is" is
   usually an improvement.

5. Check the templates, docs, and settings for exact values. Ports, statuses,
   endpoints, limits, and hostnames must be correct.

6. Group commits that deliver one outcome. Aim for 3 to 7 feature entries.
   Order them by the day they landed on main.

7. If the user impact of a change is unclear, ask the user rather than
   guessing. Never invent metrics, quotes, customers, or dates.

## Voice and layout

Write a station log. The narrator runs a subspace relay station, not a
Galaxy-class cruiser. Take the tone from Deep Space Nine: a remote station
where traffic passes through, the crew keeps the boards green, and the quiet
hours matter as much as the busy ones. Keep the bit light. The product facts
are the point, not the fiction.

Draw on the station, not the starship. Ops, the docking ring, the promenade,
traffic through the wormhole, Bajor, Cardassia, the Prophets, and the long
shift all fit. Starship language does not. No helm, no course, no warp, no
bridge, and no "the ship holds". The station holds.

- The stardate is `YYYY.DDD`, where `DDD` is the day of year of the commit's
  date on main. January 1 is 001. A non-leap year has 365 days.
- If two entries land on the same day, give the second the next stardate so
  the log reads in order.
- Open with the station frame and state how many entries follow.
- Name each heading after the station event, not the feature name. A reader
  should still learn the feature from the first sentence of the body.
- Use one section per entry.
- Put the image before the headline, always.
- Put a horizontal rule between sections. Never after the last section.
- End the file with "Station out."

## Fresh hooks

The frame repeats. The hooks do not. A reader who has seen three logs should
not be able to predict the fourth.

- Before writing, list the opening lines, section titles, closing lines, and
  metaphors from the earlier logs. Use none of them.
- Rotate the station detail. Ops one month, the promenade the next, then the
  docking ring, the replimat, the cargo bay, a quiet corridor, the wormhole.
- Keep the frame constant. The headline, stardates, image-first sections,
  dividers, and "Station out." are the format, not a joke to retell.
- When the month has no obvious station moment, use the plainest one. A quiet
  shift is a valid hook.
- The checker compares the new log against the earlier files. It fails on a
  reused intro or a reused section title.

Use this exact shape:

```markdown
---
name: October 2026
description: One sentence about the month.
image: images/get-started.png
author: Johannes Maron
date: 2026-10-21
---

# Station log, stardate 2026.294

Write one fresh opening line here. Two entries follow, in the order they
reached ops.

![Alt text that names the feature](images/sandbox-credential.png)

## Stardate 2026.270: <station event>

Body copy.

---

![Alt text that names the feature](images/message-preview.png)

## Stardate 2026.271: <another station event>

Body copy.

---

![Alt text that names the feature](images/get-started.png)

## Supplemental log

Improvements and smaller items go here. The supplemental log also gets an
image above its headline. It has no stardate.

relay is open source under AGPL-3.0. If something does not work, open an issue
on GitHub. For the full reference, read the docs.

Write one fresh closing line here.

Station out.
```

The divider sits before the next section's image. The last section has no
divider after it. Replace the month, dates, entry count, image paths, and
every `<...>` placeholder with real copy. The example is a shape, not content
to copy.

## Copy rules

- Write short sentences. One idea each.
- Do not use em dashes, en dashes, or semicolons. Use a period, a comma, or a
  colon.
- Explain what changed, then what it means for the reader.
- Include the exact values a reader needs, such as ports, statuses,
  endpoints, and limits.
- Use sentence case for headings and image alt text.
- Keep the name "relay" lowercase.
- Skip hype. No "revolutionary", "seamless", or "game-changing".
- Do not name internal tasks, services, or deploy steps unless the reader
  needs them.

## Mistakes to avoid

The first edition taught these. Do not relearn them.

- A picture below its headline. The image always goes first.
- A horizontal rule after the last section.
- A light screenshot in a dark log.
- A wide page shot with no focus. Crop to the control or card.
- A stardate entry for an improvement or an internal fix. Demote it, or cut
  it.
- A reused opening line, section title, or closing line from an earlier log.
- "Captain's log", "the ship holds course", helm, course, warp, or bridge.
- Em dashes, en dashes, or semicolons.
- A social image that does not stand on its own at 1280x640.

## Screenshots

Every section starts with a picture above its headline. Capture the picture
from the running product, not a mockup.

- Fix the viewport at 1280x640. This is a hard requirement.
- Capture every screenshot in dark mode. Emulate `prefers-color-scheme: dark`
  before navigating. The product and the email templates both ship dark
  styles, so the images stay consistent.
- Set `image` in the frontmatter to a screenshot that stands on its own in a
  social post. Use `images/<name>.png`, the same relative path the body uses.
- Keep it narrow. One control, one card, or one panel. A wide page shot that
  shows everything up close shows nothing.
- Remove the breadcrumb, footer, debug toolbar, and sticky topbar when they
  eat the frame. Keep the sidebar or a page title when it helps the reader
  recognize the screen.
- Use fixture data with realistic names and dates. Open dialogs, choose the
  option the copy talks about, and fill sample values.
- Do not ship a broken map, a missing image, or a debug toolbar. Change the
  framing or pick another view.
- Save as `product/updates/images/<kebab-case>.png`.
- Write alt text that names the feature, not "screenshot".

For relay's capture recipe, read `references/screenshots.md`.

## Validate

Run the bundled checker before handing the report over:

```shell
uv run python skills/product-updates/scripts/verify_update.py product/updates/2026-10.md
```

It checks the frontmatter and its social image, the image-before-headline
rule, the 1280x640 image size, the divider count, repeated hooks, banned
punctuation, and the closing line.

Then do a human pass:

- Read the file top to bottom as a user.
- Re-read every stardate entry. If the reader cannot reach a new screen,
  control, or capability, demote it to the supplemental log. If the reader
  cannot act on it at all, cut it.
- Compare the log with the one before it. A shared opening line, section
  title, closing line, or metaphor is a failure, even when the checker
  misses it.
- Open every image and confirm the feature is visible, the frame is not cut
  awkwardly, and the image is in dark mode.
- Confirm every claim against the code or the docs.
- If the report reveals behavior that is not documented, update `docs/docs/`
  in the same change.
- Confirm `.gitattributes` marks `product/updates/**` as
  `linguist-generated`.
- Confirm `/station-log/<slug>/` renders the update and its screenshots.
- Doc-only changes need no Django checks. If you also touch code, run
  `uv run python manage.py check` and
  `uv run python manage.py makemigrations --check --dry-run`.
