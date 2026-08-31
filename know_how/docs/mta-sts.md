---
name: MTA-STS
description: Enforce TLS for incoming mail connections
author: Johannes Maron
---

# MTA-STS

> **TL;DR**: MTA-STS tells sending mail servers to use TLS when they connect to your mail server. It prevents downgrade attacks and man-in-the-middle interception.

## What is MTA-STS?

MTA-STS (SMTP MTA Strict Transport Security) is a standard that lets a receiving mail server declare its support for TLS encryption. Sending mail servers read the MTA-STS policy and refuse to deliver over an unencrypted connection when the policy mode is `enforce`.

MTA-STS is defined in [RFC 8461][rfc-8461].

## Why MTA-STS matters

SMTP supports the `STARTTLS` command to upgrade a plain-text connection to TLS. However, `STARTTLS` is opportunistic. The connection starts in plain text, and the upgrade is optional. An attacker can block the `STARTTLS` command and force the servers to communicate in plain text. This attack is called a downgrade or STARTTLS stripping attack.

MTA-STS solves this problem. A sending server that has seen the MTA-STS policy knows that the receiving server supports TLS. If the sending server cannot establish a TLS connection, it refuses to deliver the message instead of falling back to plain text.

MTA-STS is the email equivalent of HTTP Strict Transport Security (HSTS).[^hsts] HSTS tells browsers to always use HTTPS. MTA-STS tells mail servers to always use TLS.

## How MTA-STS works

MTA-STS has three components. A DNS TXT record at `_mta-sts.<domain>` holds a policy ID. When you change the policy, you update this ID so senders fetch the new file. A policy file, served over HTTPS at `https://mta-sts.<domain>/.well-known/mta-sts.txt`, sets the TLS mode and the valid MX hosts. A CNAME record for `mta-sts.<domain>` points to the host that serves that file.

### The policy file

The policy file is a plain-text file with key-value pairs. It contains these fields:

| Field     | Purpose                          | Example                         |
| --------- | -------------------------------- | ------------------------------- |
| `version` | Protocol version                 | `STSv1`                         |
| `mode`    | Enforcement mode                 | `enforce`, `testing`, or `none` |
| `mx`      | Allowed MX host pattern          | `*.example.com`                 |
| `max_age` | Policy cache duration in seconds | `604800` (7 days)               |

### Policy modes

The `mode` field takes three values. In `testing`, the sending server records TLS failures but still delivers the message. Use this mode to monitor problems before you enforce the policy. In `enforce`, the server refuses to deliver over an unencrypted or untrusted connection, queues the message, and retries later. In `none`, the policy is disabled, senders clear their cache, and delivery falls back to opportunistic `STARTTLS`.

### Policy caching

Sending servers cache the MTA-STS policy for the duration specified in `max_age`. When a sender first connects to your mail server, it fetches the policy file over HTTPS and stores it. On subsequent connections, the sender uses the cached policy without fetching the file again.

When you change the policy, you update the `id=` tag in the DNS TXT record.[^policy-id] The sender sees the new ID on the next DNS lookup and fetches the new policy file.

### Certificate validation

In `enforce` mode, the sending server validates the TLS certificate of the receiving mail server. The certificate must be issued by a trusted certificate authority, and the hostname must match the MX record.[^dane-alternative] This prevents man-in-the-middle attacks where an attacker presents a self-signed certificate.

## How to set up MTA-STS

1. Create a policy file that lists your valid MX hosts and the enforcement mode.
1. Serve the policy file over HTTPS at `mta-sts.<domain>/.well-known/mta-sts.txt`.
1. Publish a TXT record at `_mta-sts.<domain>` with a unique policy ID.
1. Publish a CNAME record for `mta-sts.<domain>` that points to the host that serves the policy file.

Start with `mode: testing` and monitor the reports. Then switch to `mode: enforce` once you confirm that all senders can connect with TLS.

## Further reading

- [RFC 8461][rfc-8461]: SMTP MTA Strict Transport Security (MTA-STS)
- [RFC 8461][rfc-8461] Section 3.2: Policy file format
- <a href="{% url 'know_how:detail' slug='tls-rpt' %}">TLS-RPT</a>: TLS Reporting
- <a href="{% url 'know_how:detail' slug='mx' %}">MX</a>: Mail Exchange records

[^hsts]: HSTS is defined in [RFC 6797][rfc-6797]. The analogy is not exact because HSTS is enforced by browsers and MTA-STS is enforced by mail transfer agents.

[^policy-id]: The policy ID can be any unique string. A common practice is to use a short random token or a version number. Update the ID whenever you change the policy file so that senders fetch the new version.

[^dane-alternative]: DANE (DNS-Based Authentication of Named Entities) is an alternative approach to SMTP TLS that uses DNSSEC instead of certificate authorities. DANE is defined in [RFC 7672][rfc-7672]. MTA-STS and DANE can coexist, but MTA-STS is simpler to deploy because it does not require DNSSEC.

[rfc-6797]: https://www.rfc-editor.org/info/rfc6797/
[rfc-7672]: https://www.rfc-editor.org/info/rfc7672/
[rfc-8461]: https://www.rfc-editor.org/info/rfc8461/
