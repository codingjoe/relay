---
name: Alternative to Mailjet
description: How relay compares to Mailjet (Sinch) for email sending and receiving
author: Johannes Maron
---

# Alternative to Mailjet

> **TL;DR** — Mailjet is a European email API with marketing features, but DNS setup is manual and inbound is limited. relay automates DNS with a built-in nameserver, includes an MX server with webhooks, and ingests DMARC and TLS-RPT reports.

## Why choose relay over Mailjet

Mailjet (owned by Sinch, like Mailgun) is a Paris-based email service popular across Europe. It offers a templating API and marketing tools. For infrastructure-first email, relay automates the parts Mailjet leaves to you.

### Built-in nameserver

Mailjet provides SPF and DKIM records for you to add to your DNS provider. relay **serves those records itself** — delegate NS, set a DMARC record, and relay publishes MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically.

### Incoming mail

Mailjet's inbound parsing is available but routes to a webhook you provide; SPF/DKIM for inbound is managed by Mailjet. relay runs an **MX server you control**, stores raw bodies in your S3, and dispatches **Standard Webhooks** with Ed25519 signatures you verify yourself.

### DMARC and TLS-RPT reports

Mailjet does not ingest DMARC or TLS-RPT reports. relay parses **RUA, RUF, and TLS-RPT reports** and displays them in a dashboard.

### Free test domain

relay ships a **free sender domain** to test deliverability before delegating a real domain. Mailjet requires a verified sender domain.

## Side-by-side comparison

| Feature                | relay                                        | Mailjet                       |
| ---------------------- | -------------------------------------------- | ----------------------------- |
| Built-in nameserver    | Yes — serves MX, SPF, DKIM, Return-Path, PTR | No — bring your own DNS       |
| DNS setup              | NS delegation + DMARC record only            | Manual SPF, DKIM records      |
| DKIM key management    | Automatic (RSA + Ed25519)                    | Manual rotation               |
| Incoming mail (MX)     | Built-in MX server, webhook dispatch         | Inbound parse (webhook)       |
| DMARC report ingestion | Built-in dashboard                           | Not available                 |
| TLS-RPT ingestion      | Built-in dashboard                           | Not available                 |
| Free test domain       | Yes                                          | No                            |
| Pricing model          | Flat per-message                             | Tiered, contact-based pricing |

## When Mailjet is the better fit

- You want marketing-campaign tools with a visual template builder.
- You need a EU-hosted provider with sub-account collaboration features.
- You use the Sinch ecosystem for SMS and email.

## Migrating from Mailjet to relay

1. Add your domain in relay and delegate NS to the relay nameservers.
1. Set the DMARC record relay provides.
1. Move SMTP/API calls to relay's per-org credentials.
1. Replace Mailjet inbound parse with relay webhook subscriptions.
