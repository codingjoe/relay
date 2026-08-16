---
name: Spam
description: Detect and reject spam with rspamd
author: Johannes Maron
---

# Spam

> **TL;DR**: rspamd scans every message relay receives and sends. High-score mail is rejected with a `550` response. Borderline outgoing mail is held for review. relay stores the score and action on each message.

## What is rspamd?

rspamd is a fast spam-filtering system. It scans a raw email message and returns a spam score and an action. The score measures how likely the message is spam. The action tells the caller what to do with the message.

rspamd uses many signals to build the score. It checks the message content, the sending reputation, and the authentication results. It also learns from a shared database of known spam.

## Why spam detection matters

Email is open by design. Anyone can send a message to any address. Without filtering, a mailbox fills with unwanted mail. Spam also wastes resources and damages the sender reputation.

relay scans both directions:

- **Incoming mail** on the <a href="{% url 'know_how:detail' slug='mx' %}">MX</a> server. This protects the receiving domain from spam.
- **Outgoing mail** on the <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a> submission server. This detects abuse from a compromised account.

## How relay integrates rspamd

relay calls rspamd over HTTP. It posts the raw message to the `/checkv2` endpoint. rspamd returns a JSON response with the `score` and the `action`.

relay uses the HTTP interface instead of a milter. The <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a> server does not support milters. HTTP is the pragmatic integration.

The rspamd URL is set with `RELAY_RSPAMD_URL`. It defaults to `http://rspamd:11334`.

### Thresholds

Two settings control the thresholds:

| Setting                     | Default | Purpose                                        |
| --------------------------- | ------- | ---------------------------------------------- |
| `RELAY_RSPAMD_REJECT_SCORE` | `15`    | Reject the message when the score reaches this |
| `RELAY_RSPAMD_HOLD_SCORE`   | `6`     | Hold the message when the score reaches this   |

The reject score is higher than the hold score. A message that reaches the reject score is spam. A message that reaches the hold score is borderline.

## How relay handles the result

The handling differs by direction.

### Incoming mail (MX)

The MX server scans each message during the `DATA` phase. It rejects the message with a `550` response when:

- rspamd returns the `reject` action, or
- the score reaches `RELAY_RSPAMD_REJECT_SCORE`.

Otherwise the server stores the message. It saves the `spam_score` and `spam_action` on the message. It also prepends two headers to the stored body:

- `X-Spam-Score`
- `X-Spam-Action`

### Outgoing mail (SMTP submission)

The SMTP server scans each submitted message during the `DATA` phase. It rejects the message with a `550` response when the score reaches `RELAY_RSPAMD_REJECT_SCORE`. This catches abuse from a compromised account.

Otherwise the server stores the message. When the score reaches `RELAY_RSPAMD_HOLD_SCORE`, the server marks the message as `HELD`. A held message waits for review instead of being delivered. Below the hold score, the message is `PENDING` and delivers normally.

## Where the spam fields live

The `spam_score` and `spam_action` fields live on the shared `Message` model. Both `IncomingMessage` and `OutgoingMessage` inherit them. This keeps the fields consistent across both directions.

## Further reading

- [rspamd documentation](https://rspamd.com/doc/)
- <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a>: Simple Mail Transfer Protocol
- <a href="{% url 'know_how:detail' slug='mx' %}">MX</a>: Mail Exchange records
