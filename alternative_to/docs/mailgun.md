---
name: Alternative to Mailgun
description: How relay compares to Mailgun (Sinch) — all-in-one email sending, receiving, and monitoring, EU-hosted
author: Johannes Maron
---

# Alternative to Mailgun

> relay is the all-in-one email platform — sending, receiving, and reputation monitoring in one EU-hosted service. Mailgun is a developer-focused SMTP/API provider, but DNS records are manual, inbound routing is limited, and DMARC tooling is a separate product.

## Why choose relay over Mailgun

Mailgun (now part of Sinch) is popular among developers for its API and SMTP relay. It handles outbound and offers inbound routes, but the DNS and reputation side still lands on your plate.

### All-in-one monitoring

Mailgun's DMARC analytics are part of a separate deliverability product. relay ingests **DMARC RUA/RUF and TLS-RPT reports** as first-class data, parsed and displayed in your dashboard — no separate product, no forwarding setup.

### Sending reliability without DNS busywork

Mailgun generates SPF, DKIM, and tracking CNAME records for you to paste into your DNS provider, and DKIM key rotation is on you. relay automates all of it: delegate NS and set one DMARC record, and relay serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically. The built-in nameserver is the mechanism — you never touch a DNS dashboard beyond the initial delegation.

### Incoming mail

Mailgun Routes forward inbound mail to a URL or storage, but DKIM/SPF verification for inbound is managed by Mailgun's infrastructure, not yours. relay runs an **MX server you control**, stores raw bodies in your own S3, and dispatches **Standard Webhooks** with Ed25519 signatures you can verify with a public key you hold.

### EU data sovereignty

Mailgun is owned by Sinch, a Swedish (EU) company, and offers EU data residency. Here relay and Mailgun are on equal footing — both EU-based and GDPR-aligned. relay adds a **Germany-hosted** stack with local support and no US data path.

### Free test domain

relay ships a **free sender domain** to test deliverability before delegating a real domain. Mailgun requires a verified domain and offers a sandbox with restricted sending.

## Side-by-side comparison

| Feature               | relay                                         | Mailgun                             |
| --------------------- | --------------------------------------------- | ----------------------------------- |
| All-in-one monitoring | DMARC + TLS-RPT reports parsed and visualized | Separate deliverability product     |
| Sending reliability   | Automated SPF, DKIM, DMARC, no DNS dashboard  | Manual DNS records, manual rotation |
| Incoming mail (MX)    | Built-in MX server, webhook dispatch          | Routes (URL/storage)                |
| EU data sovereignty   | EU-hosted (Germany), GDPR                     | EU-hosted (Sinch/Sweden), GDPR      |
| Free test domain      | Yes                                           | Sandbox (restricted)                |
| Pricing model         | Flat per-message                              | Tiered, feature-gated plans         |

## When Mailgun is the better fit

- You need Mailgun's large-volume SMTP relay and EU data residency options.
- You rely on Mailgun's email validation API.
- You want a single Sinch account across SMS and email.

## Migrating from Mailgun to relay

1. Add your domain in relay and delegate NS to the relay nameservers.
1. Set the DMARC record relay provides.
1. Move SMTP/API credentials to relay's per-org keys.
1. Replace Mailgun Routes with relay webhook subscriptions.
