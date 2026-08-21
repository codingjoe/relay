---
name: DMARC
description: Email authentication policy for SPF and DKIM
author: Johannes Maron
---

# DMARC

> **TL;DR**: DMARC tells receiving mail servers what to do when an email fails SPF or DKIM authentication. You set one DNS record on your root domain. The platform handles the rest.

## What is DMARC?

DMARC (Domain-based Message Authentication, Reporting, and Conformance) is an email authentication policy protocol. It builds on <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> and <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a> to give domain owners control over how receiving mail servers handle messages that fail authentication.

Without DMARC, a receiving mail server has no instructions from the domain owner. It decides on its own whether to deliver, quarantine, or reject a message that fails SPF or DKIM. DMARC solves this problem. The domain owner publishes a policy in DNS, and receivers follow that policy.

DMARC is defined in [RFC 7489](https://datatracker.ietf.org/doc/html/rfc7489).[^rfc-status]

## Why DMARC matters

Email spoofing is one of the most common attack vectors in phishing and spam. An attacker can send a message that appears to come from your domain because SMTP does not verify the sender by default. DMARC gives you three tools to fight this:

1. **Policy enforcement**: You tell receivers to reject or quarantine messages that fail authentication.
1. **Alignment**: DMARC checks that the domain in the visible From address matches the domain that SPF or DKIM verified.
1. **Reporting**: Receivers send you reports about messages that use your domain, so you can monitor for abuse.

## How DMARC works

When a receiving mail server gets a message, it performs these steps:

1. The server runs the SPF check on the envelope sender domain.
1. The server runs the DKIM check on the message signature.
1. The server checks DMARC alignment. The domain in the visible From header must match the domain that SPF or DKIM verified.
1. The server reads the DMARC policy from DNS and applies it to the result.

### The DMARC DNS record

The DMARC record is a TXT record at `_dmarc.<domain>`. It contains tags that control the policy:

| Tag     | Purpose                                       | Example                                   |
| ------- | --------------------------------------------- | ----------------------------------------- |
| `v`     | Protocol version                              | `v=DMARC1`                                |
| `p`     | Policy for the root domain                    | `p=none`, `p=quarantine`, or `p=reject`   |
| `sp`    | Policy for subdomains                         | `sp=none`                                 |
| `pct`   | Percentage of messages to apply the policy to | `pct=100`                                 |
| `rua`   | Aggregate report destination                  | `rua=mailto:dmarc@example.com`            |
| `ruf`   | Forensic report destination                   | `ruf=mailto:dmarc@example.com`            |
| `adkim` | DKIM alignment mode                           | `adkim=r` (relaxed) or `adkim=s` (strict) |
| `aspf`  | SPF alignment mode                            | `aspf=r` (relaxed) or `aspf=s` (strict)   |

### Policy values

The `p=` tag has three values:

- **`none`**: The receiver delivers all mail but still sends reports. Use this mode to monitor your authentication status before you enforce a policy.
- **`quarantine`**: The receiver sends failing messages to the spam folder. This mode reduces the impact of spoofing without blocking legitimate mail that has configuration problems.
- **`reject`**: The receiver rejects failing messages at the SMTP level. This mode gives the strongest protection but requires that all legitimate senders pass authentication.[^pct-rollout]

### Alignment

Alignment is the key concept that DMARC adds on top of SPF and DKIM. A message can pass SPF on the envelope sender domain but show a different domain in the visible From header. Without alignment, an attacker can pass SPF on their own domain while spoofing yours in the From header.

DMARC alignment has two modes:

- **Relaxed alignment**: The organizational domains must match. For example, `mail.example.com` aligns with `example.com`.[^org-domain]
- **Strict alignment**: The exact domains must match. For example, `mail.example.com` does not align with `example.com`.

## DMARC reports

DMARC specifies two report types:

### Aggregate reports (RUA)

Aggregate reports are daily XML summaries. They contain statistics about all messages that used your domain during the reporting period. Each report includes:

- The source IP address of the sending server.
- The number of messages from that source.
- Whether the messages passed or failed SPF and DKIM.
- The DMARC policy result (pass, fail, or none).

Aggregate reports help you identify all senders that use your domain. You can use this data to find unauthorized senders and to verify that your legitimate senders pass authentication.

The aggregate report format is defined in [Section 8.3 of RFC 7489](https://datatracker.ietf.org/doc/html/rfc7489#section-8.3).

### Forensic reports (RUF)

Forensic reports are copies of individual messages that failed authentication. Each report includes the message headers and, in some cases, the message body. Forensic reports help you identify the source of a specific spoofing attempt.

Not all mail servers send forensic reports because of privacy concerns. Some servers redact or omit the message content.

## How the platform uses DMARC

You set one DMARC TXT record on your root domain. The platform serves all other DNS records (SPF, DKIM, MX, and more) automatically through the built-in nameserver.

The platform uses relaxed alignment for both SPF and DKIM. This means the policy covers all subdomains of your root domain. You do not need separate DMARC records for each subdomain.

The platform collects aggregate and forensic reports for you. You can view them in the DMARC reports dashboard in your organization.

## Further reading

- [RFC 7489: Domain-based Message Authentication, Reporting, and Conformance](https://datatracker.ietf.org/doc/html/rfc7489)
- [DMARC.org: Official DMARC website](https://dmarc.org/)
- <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>: Sender Policy Framework
- <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>: DomainKeys Identified Mail

[^rfc-status]: RFC 7489 is classified as "Informational", not "Standards Track". Despite this, DMARC is widely adopted by major email providers and is the de facto standard for email authentication policy.

[^pct-rollout]: The `pct` tag lets you apply the policy to a percentage of messages. Start with `pct=1` and `p=quarantine`, then increase the percentage as you gain confidence. This staged rollout prevents sudden delivery failures for legitimate senders.

[^org-domain]: The organizational domain is extracted using the Public Suffix List. For `mail.example.com`, the organizational domain is `example.com`. For `mail.example.co.uk`, it is `example.co.uk`. See [RFC 7489 Appendix A](https://datatracker.ietf.org/doc/html/rfc7489#appendix-A) for the algorithm.
