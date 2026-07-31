---
name: Alternative to Mailgun
description: A fair 2025 comparison of relay and Mailgun (Sinch) for email sending, receiving, and monitoring
author: Johannes Maron
---

# Alternative to Mailgun

> Mailgun is a developer-friendly SMTP and API provider with inbound routes. relay adds reputation monitoring and EU hosting, and it automates the DNS setup.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    <i data-lucide="circle-check" class="size-4 text-success align-middle" aria-hidden="true"></i>
    <strong>Best for a developer SMTP/API relay with EU data residency:</strong> Mailgun
  </p>
  <p class="m-0">
    <i data-lucide="circle-check" class="size-4 text-success align-middle" aria-hidden="true"></i>
    <strong>Best for sending, receiving, and monitoring with automated DNS:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                                 | relay                                                                                                         | Mailgun                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                         | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record           |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                      | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> RSA-1024, RSA-2048, Ed25519 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> RSA only                |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                   | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record           |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Self-hosted             |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record           |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a> | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual CNAME            |
| Reputation monitoring                                                                                                                                                                                                   | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> DMARC + TLS-RPT parsed      | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Separate product        |
| Incoming mail                                                                                                                                                                                                           | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> MX + webhooks               | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Routes (URL or storage) |
| EU data sovereignty                                                                                                                                                                                                     | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> EU (Germany), GDPR          | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> EU (Sinch, Sweden)                |
| Free test domain                                                                                                                                                                                                        | <i data-lucide="circle-check" class="size-4 text-success" aria-hidden="true"></i> Yes                         | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Sandbox, restricted     |
| Pricing                                                                                                                                                                                                                 | Flat per message                                                                                              | Tiered, feature-gated                                                                                               |

## What Mailgun does well

Mailgun (now part of Sinch) is popular with developers for its API and SMTP relay. As of 2025, it handles both outbound and inbound, and it offers an email validation API. Sinch is a Swedish company, so Mailgun is EU-owned and offers EU data residency.

The trade-off is the manual side. DNS records are paste-it-yourself. DKIM key rotation is on you. DMARC analytics live in a separate deliverability product.

## Where relay is different

### All-in-one monitoring

The DMARC analytics in Mailgun are a separate deliverability product. relay ingests DMARC and TLS-RPT reports as first-class data. It parses them and shows reputation and failure trends in your dashboard.

### Sending without DNS busywork

Mailgun generates SPF, DKIM, and tracking CNAME records for you to paste into your DNS provider. You rotate DKIM keys yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-1024, RSA-2048, and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

### Incoming mail

Mailgun Routes forward inbound mail to a URL or storage. DKIM and SPF for inbound are managed by Mailgun, not by you. relay runs an MX server that you control. It stores raw bodies in your own S3 and dispatches Standard Webhooks with Ed25519 signatures. You verify each delivery with a public key you hold.

### EU data sovereignty

Mailgun is owned by Sinch, a Swedish (EU) company, and offers EU data residency. Here, relay and Mailgun are on equal footing. Both are EU-based and GDPR-aligned. relay adds a Germany-hosted stack with local support and no US data path.

### Free test domain

relay ships a free sender domain to test deliverability before you delegate a real domain. Mailgun requires a verified domain and offers a sandbox with restricted sending.

## When Mailgun makes sense

- You need a high-volume SMTP relay with EU data residency.
- You rely on the Mailgun email validation API.
- You want one Sinch account for SMS and email.

## The bottom line

Mailgun is a capable developer email API with inbound routes. relay is the better fit when you want reputation monitoring, automated DNS, and Germany hosting in one service.

## Migrating from Mailgun to relay

1. Add your domain in relay. Delegate NS to the relay nameservers.
1. Set the DMARC record that relay gives you.
1. Move your SMTP or API calls to relay with a per-org credential.
1. Replace Mailgun Routes with relay webhook subscriptions.
