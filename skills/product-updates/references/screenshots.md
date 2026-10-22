# Relay screenshot recipe

The report uses screenshots from the running product. This recipe reproduces
the setup used for the October 2026 update: the `test` user, the `acme`
organization, and the fixture traffic.

## Prepare

```shell
uv sync
pnpm install
pnpm run build
uv run python manage.py collectstatic --noinput --no-esm
rm -f db.sqlite3
uv run python manage.py migrate
uv run python manage.py loaddata fixtures/initial_data.yaml
```

The fixture creates the `test` user, the `acme` organization, five domains,
one SMTP credential, two signing keys, and a month of messages.

Start a production-like server. Port 8000 is often taken by another checkout,
so use 8020.

```shell
DEBUG=false HOSTNAME=relays.to ALLOWED_HOSTS=relays.to,localhost \
  SECURE_SSL_REDIRECT=false SESSION_COOKIE_SECURE=false \
  CSRF_COOKIE_SECURE=false SECURE_HSTS_SECONDS=0 \
  uv run python manage.py runserver 8020 --insecure
```

This server has no debug toolbar. Use it for every app screenshot.

Create a session cookie for the `test` user. Run this with the same
`HOSTNAME` value as the server.

```shell
HOSTNAME=relays.to uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
u = get_user_model().objects.get(username='test')
s = SessionStore()
s['_auth_user_id'] = str(u.pk)
s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
s['_auth_user_hash'] = u.get_session_auth_hash()
s.save()
print(s.session_key)
"
```

In Playwright:

1. Set the viewport to 1280x640.
2. Emulate dark mode with `page.emulateMedia({ colorScheme: "dark" })`.
3. Add the `sessionid` cookie for `localhost`.
4. Set the header `X-Forwarded-Host: relays.to:8020`.
5. Open `http://localhost:8020/...`.

## Dark mode

Set the browser to dark mode before you navigate:

```js
await page.emulateMedia({
    colorScheme: "dark"
});
```

Check that the page uses the dark palette:

```js
getComputedStyle(document.body).backgroundColor;
```

The value should be near black, for example `oklch(0.145 0 0)`. The message
preview and the weekly digest follow the same color scheme, so they render
dark too.

## Frame the shot

Remove the chrome that eats the 640px height:

```js
document
    .querySelectorAll(
        'main > footer, #toaster, #djDebug, #djDebugToolbarHandle, #django-devbar',
    )
    .forEach((el) => el.remove());
document.querySelector('nav[aria-label="Breadcrumb"]')?.remove();
document.querySelector('main > header')?.remove();
```

Remove the topbar only when the feature needs the space. Without it, the
sidebar still gives context.

Scroll the feature to the top of the frame:

```js
const el = document.querySelector('.accordion > details');
window.scrollTo({
    top: el.getBoundingClientRect().top + window.scrollY - 8,
    behavior: 'instant',
});
```

`window.scrollTo` sometimes needs a second call after layout. Check
`el.getBoundingClientRect().top` before taking the screenshot.

For a page that is slightly too tall, prefer scrolling to the card over
zooming. If you must zoom, set `document.documentElement.style.zoom = '0.9'`
and keep the viewport at 1280x640. Never resize the viewport.

## Common screens

- **Getting started.** Open `/org/acme/email/`. The fixture shows the
  completed first two steps. Hide the footer and breadcrumb. The checklist
  fits the frame.
- **Credential dialog.** Open `/org/acme/email/credentials/`, click New
  Credential, type a sample name, and check Sandbox. Check that the Create
  button is inside the frame.
- **Domain records.** Open `/org/acme/email/domains/1/`. Hide the topbar and
  breadcrumb, scroll the quick start accordion to the top, and show the NS,
  SPF, DKIM, and DMARC records.
- **Message preview.** Use a message with a real HTML body, not one whose
  body was pruned. Scroll the Message card to the top, then open the client
  selector. The popover opens below the button and fits at 640px.
- **Message timeline.** Open a sent or bounced message. Hide the topbar and
  breadcrumb. The status card and timeline fit. Scroll a little when the
  timeline bottom is cut.
- **Message log.** Open `/org/acme/email/messages/`. Scroll about 120px so the
  chart and the first message row share the frame.
- **MCP.** Open `/org/acme/mcp/`. The endpoint accordion is the useful panel.
  The page fits without scrolling.

## Messages with a real body

The fixture references body files that are not checked in, so those messages
render as "Body pruned". Create a message with a real body through the test
email flow, or render it in a shell:

```python
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Organization
from domains.dkim import sign_message
from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.emails import TestEmail
from services.email.msa.handlers import add_feedback_id, store_outgoing_message
from services.email.msa.models import OutgoingMessage

org = Organization.objects.get(slug="acme")
org.save(update_fields=["slug"])  # renames the managed domain to relays.to
domain = Domain.objects.get(org=org, is_managed=True)
user = get_user_model().objects.get(username="test")
pk = uuid.uuid7()
email = TestEmail.to_user(
    user,
    domain=domain,
    message_pk=pk,
    from_email=f"postmaster@{domain.name}",
    language="en",
    base_url="https://relays.to/",
)
raw = add_feedback_id(email.message().as_bytes(), org, domain)
raw = sign_message(raw, domain)
message = store_outgoing_message(
    org=org,
    rcpt_to=user.email,
    mail_from=f"postmaster@{domain.name}",
    domain=domain,
    credential=None,
    status=OutgoingMessage.Status.SENT,
    ssl=True,
    client_ip="127.0.0.1",
    raw_bytes=raw,
    started_at=timezone.now(),
    message_pk=pk,
)
now = timezone.now()
Transmission.objects.create(
    message=message,
    status=Transmission.Status.SENT,
    code=250,
    output="250 2.0.0 OK",
    tls_mode=Transmission.TlsMode.STARTTLS,
    tls_version="TLSv1.3",
    tls_cipher="TLS_AES_256_GCM_SHA384",
    remote_host="gmail-smtp-in.l.google.com",
    started_at=now,
    finished_at=now,
)
```

Storing the message as `SENT` skips the delivery queue, so nothing leaves the
machine. Renaming the organization triggers the managed-domain signal. With
`HOSTNAME=relays.to`, the managed domain becomes `acme.open.relays.to`. Run
this before capturing screens that show the managed domain.

## Email previews

Email templates need `DEBUG=True`. Start a second server on 8030.

```shell
DEBUG=true HOSTNAME=relays.to ALLOWED_HOSTS=relays.to,localhost \
  SECURE_SSL_REDIRECT=false uv run python manage.py runserver 8030
```

Open `http://localhost:8030/emails/<slug>/?raw=1`. The raw response has no
toolbar and inlines attached images. Keep the browser in dark mode. The
email's `prefers-color-scheme` styles then render the dark variant. Show the
top of the message: headline, verdict, count, and stat cards. The chart
heading may fit. The rest of the mail is too tall for 640px.

## Clean up

Stop the servers and remove the working state:

```shell
rm -rf staticfiles .playwright-mcp
```

Never delete `db.sqlite3` or `storage/`: they hold working data. Keep
`product/updates/` and `captains_log/static/captains_log/`.

## Verify

```shell
for f in captains_log/static/captains_log/*/*.png; do
  printf "%s " "$(basename "$f")"
  sips -g pixelWidth -g pixelHeight "$f" | tail -2 | tr '\n' ' '
  echo
done
```

Every image must print `1280` and `640`, and every image must be dark. A quick
average-brightness check:

```shell
uv run --with pillow python - <<'PY'
from pathlib import Path

from PIL import Image

for path in sorted(Path("captains_log/static/captains_log").glob("*/*.png")):
    image = Image.open(path).convert("RGB")
    pixels = list(image.resize((64, 32)).get_flattened_data())
    average = sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3)
    print(f"{path.name}: {average:.1f}")
PY
```

Dark images score well below 100. A light image scores above 180. If an image
is bright, retake it with dark mode enabled. The size check uses `sips`, which
is available on macOS. If `tesseract` is available, scan for debug chrome:

```shell
tesseract captains_log/static/captains_log/2026-10/example.png stdout | grep -iE "queries|djDebug|django-devbar"
```

A hit means the screenshot contains the debug toolbar or devbar. Retake it on
the production-like server.
