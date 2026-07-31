---
name: Alternative to Amazon SES
description: How relay compares to Amazon SES — all-in-one email sending, receiving, and monitoring, EU-hosted
author: Johannes Maron
---

# Alternative to Amazon SES

> relay is the all-in-one email platform — sending, receiving, and reputation monitoring in one EU-hosted service. Amazon SES is a high-volume outbound relay that leaves DNS, inbound mail, and report analysis to you.

## Why choose relay over Amazon SES

Amazon Simple Email Service (SES) is a reliable, cheap-at-scale outbound SMTP relay. It assumes you already run your own DNS, configure authentication records by hand, and handle inbound mail and reputation monitoring elsewhere. relay puts all of that in one place.

### All-in-one monitoring

SES sends aggregate (RUA) and forensic (RUF) DMARC reports to an address you configure, but parsing and visualization are on you. relay **ingests DMARC and TLS-RPT reports**, parses them, and surfaces reputation and failure trends in a dashboard — no extra tooling, no forwarding setup.

### Sending reliability without DNS busywork

With SES you delegate DNS to your existing provider and publish SPF, DKIM, and DMARC records yourself, then rotate DKIM keys by hand. relay automates all of it: you set NS delegation and one DMARC record, and relay serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically. The built-in nameserver is the mechanism — you never touch a DNS dashboard beyond the initial delegation.

### Incoming mail

SES is outbound-only. For inbound mail you need a separate service or AWS Lambda + S3. relay runs an **MX server** that receives incoming email and dispatches it to your webhooks following the [Standard Webhooks](https://standardwebhooks.com) specification with Ed25519 signatures.

### EU data sovereignty

SES is an AWS product, US-owned and subject to US law (CLOUD Act). AWS offers European regions, but the data is still governed by a US provider. relay is **hosted in the EU** under the GDPR, with no US data dependency.

### Free test domain

SES requires a verified domain before you can send. relay gives you a **free sender domain** to test deliverability and integrations before you delegate anything.

## Side-by-side comparison

| Feature               | relay                                         | Amazon SES                              |
| --------------------- | --------------------------------------------- | --------------------------------------- |
| All-in-one monitoring | DMARC + TLS-RPT reports parsed and visualized | Forwarded to an address, no UI          |
| Sending reliability   | Automated SPF, DKIM, DMARC, no DNS dashboard  | Manual DNS records, manual key rotation |
| Incoming mail (MX)    | Built-in MX server, webhook dispatch          | Not available                           |
| EU data sovereignty   | EU-hosted, GDPR, no US dependency             | US-owned, US law applies                |
| Free test domain      | Yes                                           | No                                      |
| Pricing model         | Flat per-message, no infrastructure overhead  | Per-message, plus AWS infra costs       |

## When Amazon SES is the better fit

- You already run DNS on Route 53 and want everything in one AWS account.
- You send very high volume and need SES's marginal per-message pricing.
- You have a dedicated team to manage DKIM rotation and DMARC parsing.

## Migrating from Amazon SES to relay

1. Add a domain in relay and delegate NS to the relay nameservers.
1. Publish your DMARC record (relay shows you the exact value).
1. Point your application's SMTP submission at relay with a per-org credential.
1. Configure webhooks for any inbound mail you previously handled via S3/Lambda.
