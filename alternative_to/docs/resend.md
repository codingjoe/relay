---
name: Alternative to Resend
description: A fair 2026 comparison of relay and Resend for email sending, receiving, and monitoring
author: Johannes Maron
---

{% load abstract %}

# Alternative to Resend

> Resend is one of the most polished email APIs for developers, with official SDKs, React Email, and inbound receiving on every plan. relay matches the developer experience and adds automated DNS, DMARC and TLS-RPT monitoring, and EU-only data storage.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for a polished email API with SDKs for every stack:</strong> Resend
  </p>
  <p class="m-0">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for automated DNS, reputation monitoring, and EU-only storage:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                    | relay                                                                          | Resend                                                                                        |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                         | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                 |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                      | {% tabler name="circle-check" class="text-primary" %} RSA-2048, Ed25519        | {% tabler name="circle-dashed" class="text-muted-foreground" %} RSA-1024 only                 |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                   | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                 |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-x" class="text-destructive" %} Not offered                             |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-x" class="text-destructive" %} Not offered                             |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a> | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual CNAME                  |
| Reputation monitoring                                                                                                                                                                                      | {% tabler name="circle-check" class="text-primary" %} DMARC + TLS-RPT parsed   | {% tabler name="circle-dashed" class="text-muted-foreground" %} Insights, DMARC tool separate |
| Incoming mail                                                                                                                                                                                              | {% tabler name="circle-check" class="text-primary" %} MX + webhooks            | {% tabler name="circle-check" class="text-primary" %} MX + parsed webhooks                    |
| EU data sovereignty                                                                                                                                                                                        | {% tabler name="circle-check" class="text-primary" %} EU (Germany), GDPR       | {% tabler name="circle-x" class="text-destructive" %} US-owned, US storage                    |
| Free test domain                                                                                                                                                                                           | {% tabler name="circle-check" class="text-primary" %} Yes                      | {% tabler name="circle-dashed" class="text-muted-foreground" %} Own address only              |
| Sandbox                                                                                                                                                                                                    | {% tabler name="circle-check" class="text-primary" %} Credentials, no delivery | {% tabler name="circle-dashed" class="text-muted-foreground" %} Test addresses for events     |
| Pricing                                                                                                                                                                                                    | Flat per message                                                               | Tiered plans                                                                                  |

## What Resend does well

Resend is operated by Plus Five Five, Inc., a US company. It ships official SDKs for most stacks, plus the React Email template ecosystem, a CLI, and an MCP server. Receiving is available from the free tier up, and that tier covers 3,000 messages a month. SOC 2 Type II is listed on every plan.

The trade-off is the infrastructure side. DNS records are paste-it-yourself. DKIM is a single RSA-1024 key per domain, and Resend says it does not support 2048-bit keys. It publishes no MTA-STS policy and accepts no TLS-RPT reports. DMARC reports go to an address you choose, and reading them means pasting them into their open-source analyzer, or hosting it yourself.

## Where relay is different

### All-in-one monitoring

Resend checks your message content for deliverability problems and charts your own sending. It does not read DMARC or TLS-RPT reports. relay parses RUA, RUF, and TLS-RPT reports and shows reputation and failure trends in a dashboard. You monitor abuse and deliverability without extra tooling.

### Sending without DNS busywork

Resend gives you DKIM and SPF records, plus MX or CNAME records for the Return-Path, to add to your DNS provider. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-2048 and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

### Incoming mail

Both services receive mail over MX and hand it to webhooks. Resend parses the body and the attachments and exposes them over its API. relay runs its own MX server with STARTTLS. It evaluates the sender's DMARC, seals the result with ARC, and dispatches each message to your webhooks with an Ed25519 signature, per the Standard Webhooks spec. You verify each delivery with a public key you hold, without sharing a signing secret.

### EU data sovereignty

Resend can send from Ireland, but it is a US company, and it stores account records, message content, delivery logs, and webhook payloads in the United States. Transfers rely on the Standard Contractual Clauses. relay is hosted in Germany under the GDPR, with no US data path.

### Free test domain

Resend lets you send from `onboarding@resend.dev`, but only to the address of your own account. Every other recipient needs a verified domain. relay gives each organization a managed sender domain, pre-verified and DKIM-signed from signup, so you can send before you touch DNS.

## When Resend makes sense

- You want official SDKs in your language and templates in React.
- Your team already builds with React Email and does not want to move.
- You are happy to manage DNS yourself and do not need EU-only storage.

## The bottom line

Resend is a strong developer email API, and inbound receiving is included on every plan. relay is the better fit when you want DNS, reputation monitoring, and EU hosting handled in one place.

## Migrating from Resend to relay

1. Add your domain in relay. Delegate NS to the relay nameservers.
2. Set the DMARC record that relay gives you.
3. Point your app at relay's SMTP submission with a per-org credential.
4. Replace your `email.received` webhook with a relay webhook subscription.
