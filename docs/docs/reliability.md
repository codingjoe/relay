---
name: Reliability
description: How relay tracks every message and what happens when delivery fails
author: Johannes Maron
---

# Reliability

> **TL;DR**: relay queues every message and tries each MX host in turn. Webhook deliveries retry for about three days. The dashboard shows the status of every message.

## Queued delivery

Your application submits a message, and relay stores it and enqueues the delivery. relay scans the message for spam first. A clean message goes to the recipient mail server. Every delivery attempt gets a record with the SMTP transcript of the remote server.

## A status for every message

Each message shows one status in the dashboard: held, sent, bounced, or failed. Each delivery attempt shows the SMTP response from the remote server. You can see what happened to every message without a support ticket.

## MX failover

relay resolves the MX records of the recipient domain. relay tries every MX host in order of preference. If one host does not respond, delivery continues with the next host.

## Automatic retries

Some work retries on its own, with growing delays between the attempts:

- Spam scans retry with exponential backoff, up to five times.
- Webhook deliveries follow the Standard Webhooks schedule. relay tries a webhook ten times over about three days, with delays from 5 seconds up to 24 hours.

## Health checks

relay exposes health endpoints under `/health/`. The endpoints report the state of the database, the cache, the disk, and the memory. An operator or a monitoring service can watch them.

## Error monitoring

All relay processes report errors to Sentry. The reports contain no message bodies and no credentials.

## Inbound filtering

relay scans every incoming message with rspamd. relay quarantines a message with a high spam score and shows the score in the dashboard. Clean messages go to your webhooks.
