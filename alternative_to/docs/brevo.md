---
name: Alternative to Brevo
description: A fair 2025 comparison of relay and Brevo for email sending, receiving, and monitoring
author: Johannes Maron
---

{% load abstract %}

# Alternative to Brevo

> Brevo is a European all-in-one platform for marketing, SMS, and email. relay focuses on developer email: sending, receiving, and reputation monitoring in one EU-hosted service.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for all-in-one marketing, SMS, and email:</strong> Brevo
  </p>
  <p class="m-0">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for developer email with monitoring and EU hosting:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                    | relay                                                                          | Brevo                                                                                          |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                         | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                  |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                      | {% tabler name="circle-check" class="text-primary" %} RSA-2048, Ed25519        | {% tabler name="circle-dashed" class="text-muted-foreground" %} RSA only                       |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                   | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                  |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Self-hosted                    |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                  |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a> | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual CNAME                   |
| Reputation monitoring                                                                                                                                                                                      | {% tabler name="circle-check" class="text-primary" %} DMARC + TLS-RPT parsed   | {% tabler name="circle-x" class="text-destructive" %} Not available                            |
| Incoming mail                                                                                                                                                                                              | {% tabler name="circle-check" class="text-primary" %} MX + webhooks            | {% tabler name="circle-x" class="text-destructive" %} Limited                                  |
| EU data sovereignty                                                                                                                                                                                        | {% tabler name="circle-check" class="text-primary" %} EU (Germany), GDPR       | {% tabler name="circle-check" class="text-primary" %} EU (France)                              |
| Free test domain                                                                                                                                                                                           | {% tabler name="circle-check" class="text-primary" %} Yes                      | {% tabler name="circle-x" class="text-destructive" %} No                                       |
| Sandbox                                                                                                                                                                                                    | {% tabler name="circle-check" class="text-primary" %} Credentials, no delivery | {% tabler name="circle-dashed" class="text-muted-foreground" %} Sandbox header, validates only |
| Pricing                                                                                                                                                                                                    | Flat per message                                                               | Tiered, contact-based                                                                          |

## What Brevo does well

Brevo (formerly Sendinblue) is a French company with strong adoption in Germany and France. As of 2025, it bundles marketing automation, SMS, WhatsApp, and transactional email in one platform. Its campaign builder and contact segmentation are mature.

The trade-off is the developer side. DNS authentication is paste-it-yourself. Inbound mail is limited. Brevo does not ingest DMARC or TLS-RPT reports.

## Where relay is different

### All-in-one monitoring

Brevo does not ingest DMARC or TLS-RPT reports. relay parses RUA, RUF, and TLS-RPT reports and shows reputation and failure trends in a dashboard. You monitor abuse and deliverability without extra tooling.

### Sending without DNS busywork

Brevo gives you SPF and DKIM records to add to your DNS provider. You rotate keys yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-2048 and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

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
2. Set the DMARC record that relay gives you.
3. Move transactional SMTP or API calls to relay with a per-org credential.
4. Set up relay webhooks for any inbound mail you need.
