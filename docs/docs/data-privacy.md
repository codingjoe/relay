---
name: Data privacy
description: Where relay runs, what relays stores and for how long, and what never happens to your data
author: Johannes Maron
---

# Data privacy

relay processes your message data only to deliver email and to show you
reports. The defaults follow one line: keep the data, keep it short, keep it
in Europe, and never build something on top of it. This page states what
relay runs, what relay stores, and what relay will not do.

## Hosting

All relay services run on Hetzner, in the Falkenstein data center (fsn1) in
Germany:

| Component                | Role                                   | Processes                                                     |
| ------------------------ | -------------------------------------- | ------------------------------------------------------------- |
| Web dashboard and API    | Your browser and your OAuth sign-in    | Django web application behind a TLS-terminating reverse proxy |
| Authoritative nameserver | DNS for your sender domains            | DNS proxy (dnsdist) and dnslib nameserver                     |
| SMTP submission          | Your message submissions               | aiosmtpd on 587 and 465                                       |
| MX                       | Inbound delivery on 25                 | aiosmtpd, STARTTLS                                            |
| Task worker              | Asynchronous delivery, scans, webhooks | Threadmill task runner                                        |
| PostgreSQL               | Message metadata, org and domain state | Postgres 18+                                                  |
| Redis                    | Caching and rate limiting              | Redis                                                         |
| Object storage           | Raw message bodies                     | S3-compatible storage in the same region                      |
| Spam scoring             | Content filter                         | rspamd, cluster-internal                                      |

No component of this stack belongs to a provider in a third country. There
are no third-country data transfers.

## What relay stores, and for how long

| Data                                          | Where                             | How long                                              |
| --------------------------------------------- | --------------------------------- | ----------------------------------------------------- |
| Raw message bodies                            | Object storage                    | Only for delivery, deletion after successful delivery |
| Message metadata                              | PostgreSQL                        | 30 days                                               |
| Message headers (DKIM signatures, sender IPs) | PostgreSQL                        | With the retention of the message metadata            |
| SMTP and webhook transcripts                  | PostgreSQL, with the message      | With the message retention                            |
| DMARC, TLS-RPT, webhook-delivery records      | PostgreSQL                        | With the retention of the message metadata            |
| Suppression list                              | PostgreSQL, salted SHA-256 hashes | Until you remove the entry                            |

The binding legal text is the <a href="{% url 'legal:privacy' %}">privacy
policy</a>. This table describes how the platform implements it.

## What relay never stores

- **Plain suppressed addresses.** A suppression entry is a salted SHA-256
  hash of the lowercased address. relay can compare, but not read back.
- **The message body inside webhook payloads.** A delivery carries the event
  and a storage URL. The body never travels inline.
- **Passwords.** GitHub OAuth signs in, and relay stores no password at all.
- **API keys in plain form.** The database holds prefixes and hashes. The
  plain key is visible once at creation.
- **Customer-supplied Feedback-IDs.** relay replaces them with its own token
  at submission. Only the token relay actually forwarded with is stored.

## Error monitoring with boundaries

Sentry is off by default. When operators enable it, the reports contain no
message bodies, tokens, or credentials. Message content does not travel to
reporting infrastructure.

## What relay does not do with your data

- no profiling of your senders or recipients,
- no data mining, no model training on your content,
- no sale and no resale of message data.

Processing exists for delivery, for bounces, for reports, and for the
dashboards you use. Anything else requires an explicit product
decision, not a hidden default.

## Data flows

- **GitHub OAuth** provides your identity at sign-in. relay stores your
  GitHub identity and your email address.
- **Sending requires the platform** to talk to receiving mail servers and to
  DNS resolvers. Delivery is the product.
- **Reports come in** from mailbox providers to the addresses your DMARC
  and TLS-RPT records name. relay parses them for your dashboards.

## GDPR

relay operates under GDPR rules, and the platform design supports them:
EU-only processing, short storage, data minimization, and encryptions at
rest for secrets. For legal binding commitments, read the
<a href="{% url 'legal:terms' %}">terms of service</a> and the
<a href="{% url 'legal:privacy' %}">privacy policy</a>, which also cover
your rights as a data subject.

## Related pages

- <a href="{% url 'docs:detail' slug='security' %}">Security</a>. Access
  control and key protection.
- <a href="{% url 'docs:detail' slug='encryption' %}">Encryption</a>. TLS and
  key material at rest.
