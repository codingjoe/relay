---
name: Alternative to Amazon SES
description: How relay compares to Amazon SES for email sending and receiving
author: Johannes Maron
---

# Alternative to Amazon SES

> **TL;DR** — Amazon SES is a raw SMTP relay with no built-in DNS, no inbound mail, and no reputation dashboard. relay gives you a nameserver, automated DKIM/SPF/DMARC, incoming webhooks, and DMARC report ingestion — without an AWS account.

## Why choose relay over Amazon SES

Amazon Simple Email Service (SES) is a high-volume outbound SMTP relay. It is reliable and cheap at scale, but it assumes you already run your own DNS, configure authentication records by hand, and handle inbound mail elsewhere. relay removes that overhead.

### Built-in nameserver

With SES you delegate DNS to your existing provider and publish SPF, DKIM, and DMARC records yourself. relay ships an **authoritative nameserver** — you set NS delegation and a DMARC record, and relay serves MX, SPF, DKIM, Return-Path, PTR, and TLS-RPT automatically. No DNS dashboard edits beyond the initial delegation.

### Incoming mail

SES is outbound-only. For inbound mail you need a separate service or AWS Lambda + S3. relay runs an **MX server** that receives incoming email and dispatches it to your webhooks following the [Standard Webhooks](https://standardwebhooks.com) specification with Ed25519 signatures.

### DMARC and TLS-RPT reports

SES sends aggregate (RUA) and forensic (RUF) reports to an address you configure, but parsing and visualization are on you. relay **ingests DMARC and TLS-RPT reports**, parses them, and surfaces them in a dashboard.

### Free test domain

SES requires a verified domain before you can send. relay gives you a **free sender domain** to test deliverability and integrations before you delegate anything.

## Side-by-side comparison

| Feature                | relay                                        | Amazon SES                        |
| ---------------------- | -------------------------------------------- | --------------------------------- |
| Built-in nameserver    | Yes — serves MX, SPF, DKIM, Return-Path, PTR | No — bring your own DNS           |
| DNS setup              | NS delegation + DMARC record only            | Manual SPF, DKIM, DMARC records   |
| DKIM key management    | Automatic (RSA + Ed25519)                    | Manual key rotation               |
| Incoming mail (MX)     | Built-in, webhook dispatch                   | Not available                     |
| DMARC report ingestion | Built-in dashboard                           | Forwarded to an address, no UI    |
| TLS-RPT ingestion      | Built-in dashboard                           | Not available                     |
| Free test domain       | Yes                                          | No                                |
| Account requirement    | GitHub OAuth                                 | AWS account                       |
| Pricing model          | Flat per-message, no infrastructure overhead | Per-message, plus AWS infra costs |

## When Amazon SES is the better fit

- You already run DNS on Route 53 and want everything in one AWS account.
- You send very high volume and need SES's marginal per-message pricing.
- You have a dedicated team to manage DKIM rotation and DMARC parsing.

## Migrating from Amazon SES to relay

1. Add a domain in relay and delegate NS to the relay nameservers.
1. Publish your DMARC record (relay shows you the exact value).
1. Point your application's SMTP submission at relay with a per-org credential.
1. Configure webhooks for any inbound mail you previously handled via S3/Lambda.
