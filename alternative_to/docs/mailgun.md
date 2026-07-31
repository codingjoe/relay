---
name: Alternative to Mailgun
description: How relay compares to Mailgun (Sinch) for email sending and receiving
author: Johannes Maron
---

# Alternative to Mailgun

> **TL;DR** — Mailgun is a developer-focused SMTP/API provider, but DNS records are manual, inbound routing is limited, and DMARC tooling is a separate product. relay's built-in nameserver automates all authentication, includes an MX server with webhooks, and ingests DMARC and TLS-RPT reports natively.

## Why choose relay over Mailgun

Mailgun (now part of Sinch) is popular among developers for its API and SMTP relay. It handles outbound and offers inbound routes, but the DNS and reputation side still lands on your plate.

### Built-in nameserver

Mailgun generates the SPF, DKIM, and tracking CNAME records for you to paste into your DNS provider. relay **serves those records itself** — delegate NS, set a DMARC record, and relay publishes MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically.

### Incoming mail

Mailgun Routes forward inbound mail to a URL or storage, but DKIM/SPF verification for inbound is managed by Mailgun's infrastructure, not yours. relay runs an **MX server you control**, stores raw bodies in your own S3, and dispatches **Standard Webhooks** with Ed25519 signatures you can verify with a public key you hold.

### DMARC and reputation

Mailgun's DMARC analytics are part of a separate product (Deliverability Analytics). relay ingests **DMARC RUA/RUF and TLS-RPT reports** as first-class data, parsed and displayed in your dashboard.

### Free test domain

relay ships a **free sender domain** to test deliverability before delegating a real domain. Mailgun requires a verified domain and has a sandbox with restricted sending.

## Side-by-side comparison

| Feature                | relay                                        | Mailgun                          |
| ---------------------- | -------------------------------------------- | -------------------------------- |
| Built-in nameserver    | Yes — serves MX, SPF, DKIM, Return-Path, PTR | No — bring your own DNS          |
| DNS setup              | NS delegation + DMARC record only            | Manual SPF, DKIM, tracking CNAME |
| DKIM key management    | Automatic (RSA + Ed25519)                    | Manual rotation                  |
| Incoming mail (MX)     | Built-in MX server, webhook dispatch         | Routes (URL/storage)             |
| DMARC report ingestion | Built-in dashboard                           | Separate deliverability product  |
| TLS-RPT ingestion      | Built-in dashboard                           | Not available                    |
| Free test domain       | Yes                                          | Sandbox (restricted)             |
| Pricing model          | Flat per-message                             | Tiered, feature-gated plans      |

## When Mailgun is the better fit

- You need Mailgun's large-volume SMTP relay and EU data residency options.
- You rely on Mailgun's email validation API.
- You want a single Sinch account across SMS and email.

## Migrating from Mailgun to relay

1. Add your domain in relay and delegate NS to the relay nameservers.
1. Set the DMARC record relay provides.
1. Move SMTP/API credentials to relay's per-org keys.
1. Replace Mailgun Routes with relay webhook subscriptions.
