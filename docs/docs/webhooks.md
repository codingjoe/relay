---
name: Webhooks
description: Standard Webhooks deliveries with Ed25519 signatures, verification code, and the retry schedule
author: Johannes Maron
---

# Webhooks

relay hands inbound email to your application over HTTPS. Deliveries follow
the [Standard Webhooks](https://standardwebhooks.com) specification, one
signature keypair per webhook, flat JSON payloads, and a defined retry
schedule. This page is the reference for everything on the wire.

## Structure

A webhook belongs to a receiving domain, matches recipient addresses with a
glob pattern, and points at one HTTPS URL:

- **Receiving domain**. The domain whose MX points at your sender subdomain,
  for example `app.acme.com`.
- **Address pattern**. A glob over the recipient address, for example
  `*@app.acme.com`, `support@acme.com`, or `bill+*@acme.com`. A pattern is
  optional. A webhook without a pattern receives everything for its domain.
- **URL**. Must use HTTPS.
- **One keypair per webhook**. Each webhook derives its own Ed25519 signing
  key. Public keys display in `whpk_` form, and you use them to verify.

relay checks the MX record of the webhook automatically. A broken MX record is
visible on the webhook page.

## The payload

The body is flat JSON, and the raw message body is never inlined:

```json
{
  "type": "email.received",
  "message_id": "0198b7c2-7c11-7000-8000-3b9bb91234af",
  "sender": "ann@example.net",
  "recipient": "kim@app.acme.com",
  "subject": "Quote request",
  "rfc822_message_id": "<ab12@example.net>",
  "received_with_tls": true,
  "receiving_domain": "app.acme.com",
  "body_url": "https://storage.relay.example.com/msg-0199....eml",
  "spam_score": 1.5,
  "spam_action": "no action",
  "received_at": "2026-08-29T09:41:18Z"
}
```

`message_id` is the relay message id. `spam_score` and `spam_action` carry
the rspamd result. Test deliveries (from the dashboard button) use type
`email.test`, with most fields empty, so you can build your endpoint before
real mail arrives.

## Delivery headers

relay signs each delivery and sends four headers:

| Header              | Value                               | Example           |
| ------------------- | ----------------------------------- | ----------------- |
| `webhook-id`        | `msg_<uuidv7>`, unique per delivery | `msg_0199ac21...` |
| `webhook-timestamp` | Unix seconds at signing             | 1787986278        |
| `webhook-signature` | `v1a,<base64 Ed25519 signature>`    | `v1a,2lR0...`     |
| `Content-Type`      | `application/json`                  |                   |

The signed content is `{id}.{timestamp}.{body}`. The signature is an Ed25519
signature of that byte string with the webhook's private key.

## Verify a delivery

Do not trust deliveries without verification. The URL is the only secret the
sender needs. Any Standard Webhooks SDK does the job:

```python
import json

from standardwebhooks import Webhook

wh = Webhook(webhook_public_key)  # whpk_... string


def handler(payload: bytes, headers: dict[str, str]) -> None:
    event = wh.verify(payload, headers)  # raises on a bad signature
    body = json.loads(payload)
    if body["type"] == "email.received":
        fetch(body["body_url"])  # signed download URL for the raw message
```

SDKs with the same semantics exist for Node, Go, Ruby, Elixir, Rust, and
more. Verification with `wh.verify` checks the timestamp for you, so replayed
deliveries fail as well.

## The delivery record

relay stores each POST attempt as a webhook delivery: the target URL, the
response code, the response body excerpt (2,000 characters), and the
delivery status. The dashboard shows these per inbound message, so every
delivery is auditable afterwards.

## Timeout and retry

relay allows 30 seconds per POST and expects a 2xx answer for success.
Deliveries follow the Standard Webhooks schedule, with a random 0 to 29
seconds of jitter added to each delay:

| Attempt | Delay     | Approximate total  |
| ------- | --------- | ------------------ |
| 1       | immediate | 0 s                |
| 2       | 5 s       | 5 s                |
| 3       | 5 min     | 5 min              |
| 4       | 30 min    | 35 min             |
| 5       | 2 h       | 2 h 35 min         |
| 6       | 5 h       | 7 h                |
| 7       | 10 h      | 17 h               |
| 8       | 14 h      | 31 h               |
| 9       | 20 h      | 51 h               |
| 10      | 24 h      | 75 h, about 3 days |

Ten attempts, spread over roughly three days, with jitter on every delay.
If no attempt ever succeeds, relay marks the message as
`webhook_failed`. Successful deliveries mark the message as `webhook_sent`.

## Handling and re-delivery

A webhook that answers 2xx within the timeout is done. Anything else
(connection refusal, 4xx, 5xx, timeout) is a failure and retries on the
schedule above. Handle deliveries idempotently, and dedupe on `webhook-id`, because
relay can retry deliveries.
Trigger test deliveries with `email.test` from the dashboard without waiting
for real inbound mail.

## Security model

The private signing key stays encrypted in the relay database. The public
keys show in the dashboard and rotate only with a new webhook. Signatures
identify the webhook and its timestamp, so your endpoint verifies both.

## A complete receiving endpoint

FastAPI example:

```python
from fastapi import FastAPI, Request, HTTPException
from standardwebhooks import Webhook

app = FastAPI()
wh = Webhook(WEBHOOK_PUBLIC_KEY)


@app.post("/mail")
async def mail(request: Request):
    payload = await request.body()
    try:
        event = wh.verify(payload, dict(request.headers))
    except Exception:
        raise HTTPException(401, "bad signature")
    try:
        process(json.loads(payload))
    finally:
        return {"ok": True}
```

Return 2xx on accepted event, so relay stops retrying. Do the slow work
afterwards. Answer asynchronously where possible.

## Related pages

- <a href="{% url 'docs:detail' slug='receiving' %}">Receiving</a>. What
  qualifies a message for webhooks.
- <a href="{% url 'docs:detail' slug='security' %}">Security</a>. Key
  storage and rotation.
