---
name: Receiving
description: How the relay MX server accepts inbound mail and hands it to your webhooks
author: Johannes Maron
---

# Receiving

relay operates a real MX server. Any internet mail server can deliver a
message to your delegated or managed domains. relay validates the recipient,
checks the message's own authentication claims, filters spam, and dispatches
the result to your webhooks. This page explains each stage.

## The one-time receiving-domain setup

Point the MX record of your receiving domain at your sender subdomain, for
example `MX app.acme.com` to `mail.relay.acme.com`. The relay nameserver
serves that subdomain's zone, so the MX host and its TLS records exist
without further work. The dashboard's webhook check shows a wrong MX
record, with the observed value and the time of the last check.

Inbound flow:

```mermaid
sequenceDiagram
    participant Sender as Any mail server
    participant MX as relay MX (25)
    participant Store as Storage
    participant Scan as rspamd
    participant Hook as Your webhook

    Sender->>MX: STARTTLS on 25, RCPT TO
    MX->>MX: recipient-domain lookup
    MX-->>Sender: 250 / 550 not authorized
    Sender->>MX: DATA with the message
    MX->>MX: DMARC evaluation of the sender
    MX-->>Sender: 250 accepted (or 550 per policy)
    MX->>Store: store message and metadata
    MX->>Scan: spam scan
    Scan-->>MX: score and action
    MX->>Hook: signed webhook per configured endpoint
```

## The acceptance gates

**Recipient check.** relay accepts only domains registered to your
organization, resolved through the root domain, including managed domains.
Anything else answers `550 Relay not authorised for this recipient`.

**Inbound DMARC.** relay reads the DMARC policy of the message's own sender
domain. A `p=reject` policy fails the SMTP transaction with
`550 Message rejected by DMARC policy`. The message never enters the
platform. Quarantine policies mark the stored message as quarantined. This
protects senders that publish strict policies from having their name abused,
and it protects your inbox from spoofing attempts. relay signs outgoing mail
with RSA-2048 and Ed25519 keys, but inbound DKIM verification still accepts
signatures from older senders that use RSA-1024 keys.

**Spam scan.** rspamd scores every accepted message. A message whose
score reaches the reject threshold, or whose action is reject, lands as
quarantined and never reaches your webhook. You can see the score in the
dashboard.

## Special recipient addresses

Your delegated domain receives report traffic automatically:

| Address                    | Purpose                         | What relay does                              |
| -------------------------- | ------------------------------- | -------------------------------------------- |
| `dmarc@{sender-subdomain}` | DMARC aggregate reports (RUA)   | Store, parse the XML, show in the dashboard  |
| `ruf@{sender-subdomain}`   | DMARC failure reports (RUF/ARF) | Store, parse, show in the dashboard          |
| `tls@{sender-subdomain}`   | TLS-RPT reports                 | Store, parse the JSON, show in the dashboard |
| `postmaster` (+extensions) | Human mail to postmaster        | Store, and notify your team                  |

These addresses exist because your DMARC and DNS records must name a
collector, and relay is that collector. You see who authenticates as your
domain, who fails, and which servers have TLS trouble.

The MAIL-lifetime of a normal message begins at acceptance. relay stores
it with its metadata, marks it received (or quarantined), and processes it
asynchronously.

## What happens after the spam scan

A clean message goes to the matching active webhooks of the receiving domain.
The dispatch rules:

- the webhook must belong to the receiving domain, and its address pattern,
  for example `*@app.acme.com` or `support@acme.com`, matches the recipient,
- relay delivers the message to each matching webhook with the Standard
  Webhooks
  signature scheme,
- without active billing the status becomes dropped, without matching
  webhooks it becomes dropped as well.

If no webhook matches, the message stays stored with the status DROPPED, and
you can still read it in the dashboard.

## Postmaster handling

relay stores messages to `postmaster@{your-domain}` and dispatches them
like any other, with one addition: relay notifies the organization's members about
postmaster mail, because RFC 5321 requires postmaster to be reachable.

## Reading arriving mail

The dashboard lists all inbound messages with sender, recipient, TLS state,
spam score, and status. The raw message lives in storage and stays reachable
from the dashboard view. Retention follows the
<a href="{% url 'docs:detail' slug='data-privacy' %}">data-privacy</a> page.

## Related pages

- <a href="{% url 'docs:detail' slug='webhooks' %}">Webhooks</a>. Payload,
  signatures, and retry behavior.
- <a href="{% url 'docs:detail' slug='domains' %}">Managed domains and
  DNS</a>. How the MX record gets proper delegation.
