---
name: Alternative to SendGrid
description: How relay compares to SendGrid (Twilio) for email sending and receiving
author: Johannes Maron
---

# Alternative to SendGrid

> **TL;DR** — SendGrid is a popular marketing + transactional API, but DNS authentication is manual, inbound mail is a paid add-on, and DKIM rotation is on you. relay automates DNS end-to-end with a built-in nameserver, includes inbound webhooks, and ingests DMARC reports.

## Why choose relay over SendGrid

SendGrid (owned by Twilio) is one of the most widely used email APIs. It covers marketing campaigns and transactional mail. But like most providers, it leaves DNS configuration and authentication record management to you.

### Built-in nameserver

SendGrid asks you to add SPF, DKIM, and DMARC records to your DNS provider. relay **is the DNS provider** — delegate NS and set one DMARC record, and relay serves every authentication record automatically, including Return-Path and PTR.

### Incoming mail

SendGrid's Inbound Parse is available but routes to a webhook URL you provide; DKIM/SPF for inbound are your responsibility. relay runs its own **MX server** with STARTTLS, parses the message, stores the raw body in S3, and delivers signed webhook events with Ed25519 keys.

### DKIM and DMARC automation

SendGrid supports DKIM but key rotation is manual and provider-specific. relay manages **RSA-2048, RSA-1024, and Ed25519** keypairs and rotates them for you. DMARC and TLS-RPT reports are ingested and shown in the dashboard — SendGrid only forwards RUA reports to an address you choose.

### Free test domain

relay includes a **free sender domain** for deliverability testing before you delegate a real domain. SendGrid requires a verified sender identity first.

## Side-by-side comparison

| Feature                | relay                                        | SendGrid                         |
| ---------------------- | -------------------------------------------- | -------------------------------- |
| Built-in nameserver    | Yes — serves MX, SPF, DKIM, Return-Path, PTR | No — bring your own DNS          |
| DNS setup              | NS delegation + DMARC record only            | Manual SPF, DKIM, DMARC records  |
| DKIM key management    | Automatic (RSA + Ed25519)                    | Manual rotation                  |
| Incoming mail (MX)     | Built-in MX server, webhook dispatch         | Inbound Parse (add-on)           |
| DMARC report ingestion | Built-in dashboard                           | Forwarded, no UI                 |
| TLS-RPT ingestion      | Built-in dashboard                           | Not available                    |
| Free test domain       | Yes                                          | No                               |
| Pricing model          | Flat per-message, no tiers                   | Tiered plans, separate marketing |

## When SendGrid is the better fit

- You need a full marketing-campaign builder with templates and contact lists.
- You rely on SendGrid's large ecosystem of integrations and SDKs.
- You want a single Twilio account for SMS + email.

## Migrating from SendGrid to relay

1. Add your domain in relay and delegate NS to the relay nameservers.
1. Set the DMARC record relay gives you.
1. Switch your app's SMTP/API calls to relay's per-org credentials.
1. Point inbound webhooks at relay instead of SendGrid Inbound Parse.
