---
name: Alternative to SendGrid
description: A fair 2025 comparison of relay and SendGrid (Twilio) for email sending, receiving, and monitoring
author: Johannes Maron
---

{% load static %}

# Alternative to SendGrid

> SendGrid is one of the most popular email APIs, with strong marketing tools. relay focuses on sending, receiving, and reputation monitoring in one EU-hosted service.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    <svg class="tabler size-4 text-primary align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg>
    <strong>Best for marketing campaigns and a large integration ecosystem:</strong> SendGrid
  </p>
  <p class="m-0">
    <svg class="tabler size-4 text-primary align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg>
    <strong>Best for sending, receiving, and monitoring in one EU-hosted service:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                                                                                                               | relay                                                                                                                                                                              | SendGrid                                                                                                                                                                                         |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a>                         | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Auto-served              | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Manual record                |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a>                      | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> RSA-2048, Ed25519        | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> RSA only                     |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a>                   | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Auto-served              | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Manual record                |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a>             | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Auto-served              | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Self-hosted                  |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a>             | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Auto-served              | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Manual record                |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path. Know how"><svg class="tabler size-3.5 align-middle" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-info-circle"></use></svg></a> | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Auto-served              | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Manual CNAME                 |
| Reputation monitoring                                                                                                                                                                                                                                                                                 | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> DMARC + TLS-RPT parsed   | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Separate product             |
| Incoming mail                                                                                                                                                                                                                                                                                         | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> MX + webhooks            | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Inbound Parse (add-on)       |
| EU data sovereignty                                                                                                                                                                                                                                                                                   | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> EU, GDPR                 | <svg class="tabler size-4 text-destructive" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-x"></use></svg> US-owned (EU on higher tiers)          |
| Free test domain                                                                                                                                                                                                                                                                                      | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Yes                      | <svg class="tabler size-4 text-destructive" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-x"></use></svg> No                                     |
| Sandbox                                                                                                                                                                                                                                                                                               | <svg class="tabler size-4 text-primary" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-check"></use></svg> Credentials, no delivery | <svg class="tabler size-4 text-muted-foreground" aria-hidden="true"><use href="{% static 'img/tabler-icons/tabler-sprite.svg' %}#tabler-circle-dashed"></use></svg> Sandbox mode, validates only |
| Pricing                                                                                                                                                                                                                                                                                               | Flat per message                                                                                                                                                                   | Tiered plans                                                                                                                                                                                     |

## What SendGrid does well

SendGrid (owned by Twilio) covers marketing campaigns and transactional mail in one API. As of 2025, it has one of the largest ecosystems of integrations and SDKs. Its marketing template builder and contact tools are mature.

The trade-off is the infrastructure side. DNS authentication is manual. Inbound mail is a paid add-on. DKIM key rotation is on you. Reputation analytics live in a separate deliverability product.

## Where relay is different

### All-in-one monitoring

The deliverability insights in SendGrid are limited. The DMARC analytics are in a separate product. relay ingests DMARC and TLS-RPT reports, parses them, and shows reputation and failure trends in one dashboard.

### Sending without DNS busywork

SendGrid asks you to add SPF, DKIM, and DMARC records to your DNS provider. You rotate DKIM keys yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-2048 and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

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
2. Set the DMARC record that relay gives you.
3. Switch your app to relay with a per-org credential.
4. Point inbound webhooks at relay instead of SendGrid Inbound Parse.
