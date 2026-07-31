---
name: Alternative to Brevo
description: How relay compares to Brevo for email sending and receiving
author: Johannes Maron
---

# Alternative to Brevo

> **TL;DR** — Brevo (formerly Sendinblue) bundles marketing, SMS, and transactional email, but DNS authentication is manual and inbound mail is limited. relay automates DNS with a built-in nameserver, includes an MX server with webhooks, and ingests DMARC reports natively.

## Why choose relay over Brevo

Brevo is a European all-in-one marketing platform with strong adoption in Germany and France. It is a good choice for teams that want marketing automation alongside email. For developer-grade email infrastructure, relay removes the manual DNS and inbound-mail gaps.

### Built-in nameserver

Brevo gives you SPF and DKIM records to add to your DNS provider. relay **is the DNS provider** — delegate NS and set a DMARC record, and relay serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically. No DNS dashboard edits beyond the initial delegation.

### Incoming mail

Brevo's inbound handling is minimal — it focuses on outbound. relay runs an **MX server** that receives incoming email with STARTTLS and dispatches it to your webhooks via Standard Webhooks with Ed25519 signatures.

### DMARC and TLS-RPT reports

Brevo does not ingest DMARC or TLS-RPT reports. relay parses **RUA, RUF, and TLS-RPT reports** and surfaces them in a dashboard so you can monitor abuse and deliverability.

### Free test domain

relay includes a **free sender domain** to test deliverability and integrations. Brevo requires a verified sender identity before sending.

## Side-by-side comparison

| Feature                | relay                                        | Brevo                         |
| ---------------------- | -------------------------------------------- | ----------------------------- |
| Built-in nameserver    | Yes — serves MX, SPF, DKIM, Return-Path, PTR | No — bring your own DNS       |
| DNS setup              | NS delegation + DMARC record only            | Manual SPF, DKIM records      |
| DKIM key management    | Automatic (RSA + Ed25519)                    | Manual rotation               |
| Incoming mail (MX)     | Built-in MX server, webhook dispatch         | Limited                       |
| DMARC report ingestion | Built-in dashboard                           | Not available                 |
| TLS-RPT ingestion      | Built-in dashboard                           | Not available                 |
| Free test domain       | Yes                                          | No                            |
| Pricing model          | Flat per-message                             | Tiered, contact-based pricing |

## When Brevo is the better fit

- You need a marketing-campaign builder with automation flows and contact segmentation.
- You want SMS, WhatsApp, and email in one platform.
- You prefer a EU-hosted marketing suite with GDPR-aligned tooling.

## Migrating from Brevo to relay

1. Add your domain in relay and delegate NS to the relay nameservers.
1. Set the DMARC record relay provides.
1. Move transactional SMTP/API calls to relay's per-org credentials.
1. Set up relay webhooks for any inbound mail you need.
