---
name: SPF
description: DNS record listing authorized sending servers
author: Johannes Maron
---

# SPF

> **TL;DR**: SPF is a DNS record that lists the mail servers authorized to send email for your domain. Receiving servers check this record to verify the sender.

## What is SPF?

SPF (Sender Policy Framework) is a DNS-based email authentication standard. It lets a domain owner publish a list of IP addresses and mechanisms that identify the mail servers authorized to send email for that domain. Receiving mail servers check the SPF record to verify that the sending server is authorized.

SPF is defined in [RFC 7208][rfc-7208].

## Why SPF matters

The SMTP protocol does not verify the sender address. Any mail server can claim to send mail from any domain. This design comes from the early days of the internet, when trust was assumed. Today, this openness enables spam and phishing.

SPF closes this gap. When a receiving mail server checks SPF, it compares the sending IP address against the authorized list in DNS. If the IP is not on the list, the receiving server can reject or flag the message.

SPF is one of the two authentication methods that <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> uses. The other is <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>. DMARC requires at least one of the two to pass.

## How SPF works

The SPF check follows these steps:

1. The sending mail server connects to the receiving server and sends the `MAIL FROM` command with the envelope sender address.
1. The receiving server extracts the domain from the envelope sender address.
1. The receiving server looks up the SPF TXT record for that domain.
1. The receiving server evaluates the SPF record against the sending IP address.
1. The result is one of: `pass`, `fail`, `softfail`, `neutral`, `permerror`, or `temperror`.

The check happens during the SMTP transaction, before the message body is accepted. This means the receiving server can reject a failing message before it enters the mail system.

### The envelope sender vs. the visible From

SPF checks the envelope sender address (the `MAIL FROM` address), not the visible `From` header that the recipient sees. These two addresses can be different. A message can show `from: billing@example.com` in the headers but use `bounce@marketing.example.com` as the envelope sender. SPF checks the latter.

This distinction matters for <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> alignment, which verifies that the envelope sender domain and the visible From domain match.

### The `HELO`/`EHLO` check

SPF can also check the domain that the sending server gives in the `HELO` or `EHLO` command. This check happens before the `MAIL FROM` check.[^helo-optional] If the `HELO` domain fails SPF, some servers reject the connection before the message is sent.

## SPF record format

An SPF record is a TXT record that starts with `v=spf1`. The record contains mechanisms separated by spaces. Each mechanism can have a qualifier:

| Qualifier     | Result if matched | Example          |
| ------------- | ----------------- | ---------------- |
| `+` (default) | pass              | `+ip4:192.0.2.1` |
| `~`           | softfail          | `~all`           |
| `-`           | fail              | `-all`           |
| `?`           | neutral           | `?all`           |

### Mechanisms

| Mechanism              | Description                                        |
| ---------------------- | -------------------------------------------------- |
| `a`                    | Match the IP addresses of the domain A records     |
| `mx`                   | Match the IP addresses of the domain MX records    |
| `ip4:x.x.x.x`          | Match a specific IPv4 address or range             |
| `ip6:xxxx`             | Match a specific IPv6 address or range             |
| `include:example.com`  | Include the SPF record of another domain           |
| `exists:example.com`   | Match if the domain has an A record                |
| `redirect=example.com` | Use the SPF record of another domain as the policy |
| `all`                  | Match all remaining IP addresses                   |

The `all` mechanism is usually the last one in the record. It defines the default result for any IP address that did not match an earlier mechanism.

### Lookup limits

SPF has a DNS lookup limit of 10. Each `include`, `a`, `mx`, `exists`, or `redirect` mechanism counts as one lookup. If a record exceeds 10 lookups, the result is `permerror`.[^lookup-limit] This limit prevents DNS-based denial-of-service attacks.

## How to set up SPF

1. Collect the IP addresses of all servers that send email for your domain.
1. Create a TXT record that starts with `v=spf1`.
1. Add the `a` and `mx` mechanisms to authorize your mail servers.
1. Add `ip4:` and `ip6:` mechanisms for each additional sending IP address.
1. End the record with `~all` to soft-fail all other senders.

Use `-all` for hard fail only after you confirm that all legitimate senders pass SPF.[^softfail-vs-fail]

## Further reading

- [RFC 7208][rfc-7208]: Sender Policy Framework
- [RFC 7208][rfc-7208] Section 2.3: SPF results
- <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>: Domain-based Message Authentication, Reporting, and Conformance
- <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>: DomainKeys Identified Mail
- <a href="{% url 'know_how:detail' slug='return-path' %}">Return-Path</a>: The bounce address and envelope sender

[^helo-optional]: The `HELO`/`EHLO` check is optional in the SPF specification. A server can publish a separate SPF record for its `HELO` hostname. This practice is recommended but not required. See [RFC 7208][rfc-7208] Section 2.3.

[^lookup-limit]: The 10-lookup limit includes recursive `include` chains. If domain A includes domain B, and domain B includes domain C, each step counts toward the limit. Long include chains are a common cause of SPF `permerror` results.

[^softfail-vs-fail]: The difference between `~all` (soft fail) and `-all` (hard fail) is in the receiver response. Soft fail is a recommendation to treat the message with suspicion. Hard fail is a recommendation to reject it. Some receivers ignore the distinction and treat both the same.

[rfc-7208]: https://www.rfc-editor.org/info/rfc7208/
