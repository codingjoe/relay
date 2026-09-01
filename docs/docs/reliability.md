---
name: Reliability
description: Queued delivery, transmission records, retry schedules, and health monitoring
author: Johannes Maron
---

# Reliability

Email must survive restarts, dead MX hosts, failing endpoints, and slow
recipients. relay queues everything, records every attempt, and retries
according to definable schedules. This page is the reliability manual. It explains
the failure paths, and how you observe each of them.

## The queue model

relay stores your submission before any processing:

```mermaid
flowchart TD
    A[250 OK: message stored as pending] --> B[rspamd outbound scan]
    B -- held --> C[Status held]
    B -- clean --> D[DKIM sign all keys]
    D --> E[MX lookup, MTA-STS filter]
    E --> F[Attempt 1]
    F --> G[Status sent, transcript stored]
    E -- all hosts fail --> H[Status failed, transcript stored]
    E -- permanent 5xx --> I[Status bounced + suppression]
```

Message storage comes before any delivery logic. If a process dies between
acceptance and delivery, the message is still there: the worker picks it up
from the queue state, performs through an attempt, and records the attempt.

## Transmission records

Every accepted submission and every delivery attempt produces one immutable
transmission row with:

- the submission row records the SMTP acceptance answer and whether the
  submission arrived over TLS,

- a delivered attempt records the attempted MX host, the TLS details of the
  connection: STARTTLS or TLS, the protocol version, the cipher suite, and
  the certificate the remote server presented, identified by its SHA-256
  fingerprint, with its subject, alternative names, issuer, serial number,
  validity window, and certificate chain, and both IP addresses of the
  delivery connection: the address relay sent from and the address of the MX
  that handled the attempt,

- the SMTP status code and the complete answer text,

- a log reference for later inspection.

Failures become visible with their reasons instead of disappearing. Support
starts from those facts, not from memories.

## How failure path work

```mermaid
flowchart TD
    A[Attempt to MX host 1, preference order] -- fail --> B[Attempt host 2]
    B -- fail --> C[Attempt host n]
    C -- fail --> D[Mark failed]
    A -- 5xx permanent --> E[Mark bounced, suppress the address]
    A -- 2xx-ish success --> F[Mark sent]
```

- **Multiple MX hosts.** relay walks the MX list by preference and skips
  hosts that MTA-STS rejects, so a single broken host does not block
  delivery.
- **No MX records found** results in a clear failure, not in a silent drop.
- **Permanent (5xx) answers bounce immediately** and feed the automatic
  suppression list. No retry storm at an unwilling receiver.
- **Transient failures** surface in the transcript list, and the message
  ending in failed keeps the last answer for diagnosis.

## Automatic retry schedules

relay defines explicit retry behavior for external systems:

| Action             | Schedule                                                 | Notes                                   |
| ------------------ | -------------------------------------------------------- | --------------------------------------- |
| Outbound spam scan | Backoff 1 s to 5 min, up to 5 attempts                   | Only network errors (HTTP and OS) retry |
| Webhook delivery   | 10 attempts, immediate up to 24 h gaps, about 75 h total | 0 to 29 s jitter on every retry         |
| Inbound spam scan  | 1 s to 5 min backoff, up to 5 attempts                   | Same error classes as outbound          |

Webhook retries stop early on success. Every delivery attempt carries its
URL, response code, and a response excerpt of 2,000 characters, so an
endpoint misbehavior shows as data.

## Health endpoints

The web process exposes two health endpoints for load balancers and uptime
monitors:

| Endpoint          | Checks                               | Use                    |
| ----------------- | ------------------------------------ | ---------------------- |
| `/health/`        | Disk, memory                         | Lightweight outer loop |
| `/health/django/` | Cache, database, Redis, disk, memory | Full stack probe       |

Both answer with a status and an HTTP 200 when healthy. Monitor them with
whatever you use elsewhere. You need no special headers.

## Observability of failures

- **Errors go to Sentry**, all processes share one project, off by default.
  No message bodies, no credentials, no tokens travel there.
- **Dashboard transmissions** show each outbound attempt with its SMTP
  conversation.
- **Webhook delivery rows** show inbound webhook status.
- **Inbound quarantine** contents stay readable, with the spam score visible.

## Operational notes for high-volume senders

- Answer webhook endpoints fast. The retry schedule shows why slow endpoints
  cost you minutes-to-days of redelivery delay.
- Distinguish bounce types where it matters: a "550 mailbox unknown" answer
  in the dashboard transcript is final, do not wait it out. The suppression
  already protects you.

## Related pages

- <a href="{% url 'docs:detail' slug='sending' %}">Sending</a>. Statuses and
  SMTP replies in detail.
- <a href="{% url 'docs:detail' slug='webhooks' %}">Webhooks</a>. The full
  retry table and verification code.
