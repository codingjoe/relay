---
name: Alternative to Brevo
description: A fair 2025 comparison of relay and Brevo for email sending, receiving, and monitoring
author: Johannes Maron
---

# Alternative to Brevo

> Brevo is a European all-in-one platform for marketing, SMS, and email. relay focuses on developer email: sending, receiving, and reputation monitoring in one EU-hosted service.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    <i data-lucide="circle-check" class="size-4 text-primary align-middle" aria-hidden="true"></i>
    <strong>Best for all-in-one marketing, SMS, and email:</strong> Brevo
  </p>
  <p class="m-0">
    <i data-lucide="circle-check" class="size-4 text-primary align-middle" aria-hidden="true"></i>
    <strong>Best for developer email with monitoring and EU hosting:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                                 | relay                                                                                                         | Brevo                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                         | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                      | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> RSA-1024, RSA-2048, Ed25519 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> RSA only      |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>                   | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Self-hosted   |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a>             | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual record |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path — know how"><i data-lucide="info" class="size-3.5 align-middle" aria-hidden="true"></i></a> | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Auto-served                 | <i data-lucide="circle-dashed" class="size-4 text-muted-foreground" aria-hidden="true"></i> Manual CNAME  |
| Reputation monitoring                                                                                                                                                                                                   | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> DMARC + TLS-RPT parsed      | <i data-lucide="circle-x" class="size-4 text-destructive" aria-hidden="true"></i> Not available           |
| Incoming mail                                                                                                                                                                                                           | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> MX + webhooks               | <i data-lucide="circle-x" class="size-4 text-destructive" aria-hidden="true"></i> Limited                 |
| EU data sovereignty                                                                                                                                                                                                     | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> EU (Germany), GDPR          | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> EU (France)             |
| Free test domain                                                                                                                                                                                                        | <i data-lucide="circle-check" class="size-4 text-primary" aria-hidden="true"></i> Yes                         | <i data-lucide="circle-x" class="size-4 text-destructive" aria-hidden="true"></i> No                      |
| Pricing                                                                                                                                                                                                                 | Flat per message                                                                                              | Tiered, contact-based                                                                                     |

## What Brevo does well

Brevo (formerly Sendinblue) is a French company with strong adoption in Germany and France. As of 2025, it bundles marketing automation, SMS, WhatsApp, and transactional email in one platform. Its campaign builder and contact segmentation are mature.

The trade-off is the developer side. DNS authentication is paste-it-yourself. Inbound mail is limited. Brevo does not ingest DMARC or TLS-RPT reports.

## Where relay is different

### All-in-one monitoring

Brevo does not ingest DMARC or TLS-RPT reports. relay parses RUA, RUF, and TLS-RPT reports and shows reputation and failure trends in a dashboard. You monitor abuse and deliverability without extra tooling.

### Sending without DNS busywork

Brevo gives you SPF and DKIM records to add to your DNS provider. You rotate keys yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-1024, RSA-2048, and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

### Incoming mail

The inbound handling in Brevo is minimal. It focuses on outbound. relay runs an MX server that receives incoming email with STARTTLS. It dispatches each message to your webhooks with an Ed25519 signature, per the Standard Webhooks spec.

### EU data sovereignty

Brevo is a French company, EU-hosted and GDPR-aligned. Here, relay and Brevo are on equal footing. Both are EU-based. relay adds a Germany-hosted stack with local support and no US data path.

### Free test domain

relay includes a free sender domain to test deliverability and integrations. Brevo requires a verified sender identity before you send.

## When Brevo makes sense

- You need a marketing-campaign builder with automation flows.
- You want SMS, WhatsApp, and email in one platform.
- You prefer a EU-hosted marketing suite.

## The bottom line

Brevo is a strong all-in-one marketing platform. relay is the better fit for developer email when you want inbound mail, reputation monitoring, and automated DNS in one EU-hosted service.

## Migrating from Brevo to relay

1. Add your domain in relay. Delegate NS to the relay nameservers.
1. Set the DMARC record that relay gives you.
1. Move transactional SMTP or API calls to relay with a per-org credential.
1. Set up relay webhooks for any inbound mail you need.
