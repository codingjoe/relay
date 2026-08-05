---
name: Alternative to SendGrid
description: A fair 2025 comparison of relay and SendGrid (Twilio) for email sending, receiving, and monitoring
author: Johannes Maron
---

# Alternative to SendGrid

> SendGrid is one of the most popular email APIs, with strong marketing tools. relay focuses on sending, receiving, and reputation monitoring in one EU-hosted service.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    <i data-lucide="circle-check" class="size-4 text-primary align-middle" aria-hidden="true"></i>
    <strong>Best for marketing campaigns and a large integration ecosystem:</strong> SendGrid
  </p>
  <p class="m-0">
    <i data-lucide="circle-check" class="size-4 text-primary align-middle" aria-hidden="true"></i>
    <strong>Best for sending, receiving, and monitoring in one EU-hosted service:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                                | relay                                                                                                         | SendGrid                                                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                         | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record          |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                      | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> RSA-1024, RSA-2048, Ed25519 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> RSA only               |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                   | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record          |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Self-hosted            |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record          |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path: know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a> | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual CNAME           |
| Reputation monitoring                                                                                                                                                                                                  | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> DMARC + TLS-RPT parsed      | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Separate product       |
| Incoming mail                                                                                                                                                                                                          | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> MX + webhooks               | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Inbound Parse (add-on) |
| EU data sovereignty                                                                                                                                                                                                    | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> EU, GDPR                    | <i data-lucide="circle-x" class="size-4 text-destructive" aria-hidden="true"></i> US-owned (EU on higher tiers)    |
| Free test domain                                                                                                                                                                                                       | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Yes                         | <i data-lucide="circle-x" class="size-4 text-destructive" aria-hidden="true"></i> No                               |
| Pricing                                                                                                                                                                                                                | Flat per message                                                                                              | Tiered plans                                                                                                       |

## What SendGrid does well

SendGrid (owned by Twilio) covers marketing campaigns and transactional mail in one API. As of 2025, it has one of the largest ecosystems of integrations and SDKs. Its marketing template builder and contact tools are mature.

The trade-off is the infrastructure side. DNS authentication is manual. Inbound mail is a paid add-on. DKIM key rotation is on you. Reputation analytics live in a separate deliverability product.

## Where relay is different

### All-in-one monitoring

The deliverability insights in SendGrid are limited. The DMARC analytics are in a separate product. relay ingests DMARC and TLS-RPT reports, parses them, and shows reputation and failure trends in one dashboard.

### Sending without DNS busywork

SendGrid asks you to add SPF, DKIM, and DMARC records to your DNS provider. You rotate DKIM keys yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-1024, RSA-2048, and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

### Incoming mail

SendGrid Inbound Parse routes mail to a webhook URL you provide. DKIM and SPF for inbound are your responsibility. relay runs its own MX server with STARTTLS. It stores the raw body in S3 and delivers signed webhook events with Ed25519 keys.

### EU data sovereignty

SendGrid is a Twilio product. Twilio is a US company, and it hosts data primarily in the US. EU data residency is available only on higher tiers. relay is hosted in the EU under the GDPR, with no US data path.

### Free test domain

relay includes a free sender domain for deliverability testing before you delegate a real domain. SendGrid requires a verified sender identity first.

## When SendGrid makes sense

- You need a full marketing-campaign builder with templates and contact lists.
- You rely on the SendGrid ecosystem of integrations and SDKs.
- You want one Twilio account for SMS and email.

## The bottom line

SendGrid is a strong all-round email API with deep marketing features. relay is the better fit when you want inbound mail, reputation monitoring, and EU hosting, without manual DNS work.

## Migrating from SendGrid to relay

1. Add your domain in relay. Delegate NS to the relay nameservers.
1. Set the DMARC record that relay gives you.
1. Switch your app to relay with a per-org credential.
1. Point inbound webhooks at relay instead of SendGrid Inbound Parse.
