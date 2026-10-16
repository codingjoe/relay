---
name: Alternative to Amazon SES
description: A fair 2025 comparison of relay and Amazon SES for email sending, receiving, and monitoring
author: Johannes Maron
---

{% load abstract %}

# Alternative to Amazon SES

> Amazon SES is a solid choice for high-volume outbound email. relay adds inbound mail, reputation monitoring, and EU hosting in one service.

<div class="not-prose my-6 rounded-lg border border-border bg-card p-4 text-sm">
  <p class="m-0 mb-2">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for high-volume outbound only:</strong> Amazon SES
  </p>
  <p class="m-0">
    {% tabler name="circle-check" class="text-primary align-middle" %}
    <strong>Best for sending, receiving, and monitoring in one EU-hosted service:</strong> relay
  </p>
</div>

## Quick comparison

| Feature                                                                                                                                                                                                    | relay                                                                          | Amazon SES                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| SPF <a href="{% url 'know_how:detail' slug='spf' %}" target="_blank" rel="noopener" aria-label="SPF. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                         | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                |
| DKIM <a href="{% url 'know_how:detail' slug='dkim' %}" target="_blank" rel="noopener" aria-label="DKIM. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                      | {% tabler name="circle-check" class="text-primary" %} RSA-2048, Ed25519        | {% tabler name="circle-dashed" class="text-muted-foreground" %} RSA only                     |
| DMARC <a href="{% url 'know_how:detail' slug='dmarc' %}" target="_blank" rel="noopener" aria-label="DMARC. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>                   | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                |
| MTA-STS <a href="{% url 'know_how:detail' slug='mta-sts' %}" target="_blank" rel="noopener" aria-label="MTA-STS. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Self-hosted                  |
| TLS-RPT <a href="{% url 'know_how:detail' slug='tls-rpt' %}" target="_blank" rel="noopener" aria-label="TLS-RPT. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a>             | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual record                |
| Return-Path <a href="{% url 'know_how:detail' slug='return-path' %}" target="_blank" rel="noopener" aria-label="Return-Path. Know how">{% tabler name="info-circle" size="3.5" class="align-middle" %}</a> | {% tabler name="circle-check" class="text-primary" %} Auto-served              | {% tabler name="circle-dashed" class="text-muted-foreground" %} Manual CNAME                 |
| Reputation monitoring                                                                                                                                                                                      | {% tabler name="circle-check" class="text-primary" %} DMARC + TLS-RPT parsed   | {% tabler name="circle-dashed" class="text-muted-foreground" %} Forwarded, no UI             |
| Incoming mail                                                                                                                                                                                              | {% tabler name="circle-check" class="text-primary" %} MX + webhooks            | {% tabler name="circle-x" class="text-destructive" %} Not available                          |
| EU data sovereignty                                                                                                                                                                                        | {% tabler name="circle-check" class="text-primary" %} EU, GDPR                 | {% tabler name="circle-x" class="text-destructive" %} US-owned                               |
| Free test domain                                                                                                                                                                                           | {% tabler name="circle-check" class="text-primary" %} Yes                      | {% tabler name="circle-x" class="text-destructive" %} No                                     |
| Sandbox                                                                                                                                                                                                    | {% tabler name="circle-check" class="text-primary" %} Credentials, no delivery | {% tabler name="circle-dashed" class="text-muted-foreground" %} Sandbox, verified recipients |
| Pricing                                                                                                                                                                                                    | Flat per message                                                               | Per message + AWS infra                                                                      |

## What Amazon SES does well

Amazon SES is reliable and cheap at scale. It fits teams that already run DNS on Route 53 and want one AWS account for everything. As of 2025, it stays one of the lowest-cost outbound relays for very high volume.

The trade-off is scope. SES is outbound-only. You bring your own DNS, rotate DKIM keys by hand, and handle inbound mail and report analysis elsewhere.

## Where relay is different

### All-in-one monitoring

SES sends aggregate and forensic DMARC reports to an address you choose. You parse them yourself. relay ingests DMARC and TLS-RPT reports, parses them, and shows reputation and failure trends in a dashboard.

### Sending without DNS busywork

With SES, you publish SPF, DKIM, and DMARC records yourself. relay automates this. You delegate NS and set one DMARC record. relay then serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT for you. relay signs mail with DKIM keys in RSA-2048 and Ed25519, and it serves the MTA-STS policy over HTTPS. The built-in nameserver is the mechanism. You do not touch a DNS dashboard after the initial delegation.

### Incoming mail

SES does not receive mail. For inbound, you need a separate service or AWS Lambda with S3. relay runs an MX server that receives incoming email. It dispatches each message to your webhooks with an Ed25519 signature, per the Standard Webhooks spec.

### EU data sovereignty

SES is an AWS product. AWS is a US company, and US law applies to the data. AWS offers European regions, but the provider stays US. relay is hosted in the EU under the GDPR, with no US data path.

### Free test domain

SES requires a verified domain before you send. relay gives you a free sender domain. You can test deliverability and integrations before you delegate a real domain.

## When Amazon SES makes sense

- You already run DNS on Route 53 and want one AWS account.
- You send very high volume and need the lowest per-message cost.
- You have a team that manages DKIM rotation and DMARC parsing.

## The bottom line

Amazon SES is a strong outbound relay. relay is the better fit when you want inbound mail, reputation monitoring, and EU hosting in one service, without manual DNS work.

## Migrating from Amazon SES to relay

1. Add a domain in relay. Delegate NS to the relay nameservers.
2. Publish the DMARC record that relay gives you.
3. Point your app at relay with a per-org credential.
4. Set up webhooks for any inbound mail you handled with S3 or Lambda.
