---
name: Return-Path
description: Bounce address for email delivery notifications
author: Johannes Maron
---

# Return-Path

> **TL;DR**: The Return-Path is the email address that receives bounce messages. It is set by the sending mail server and is separate from the visible From address. The platform configures the Return-Path for you.

## What is Return-Path?

The Return-Path is the email address that receives bounce messages and delivery status notifications.[^terminology] It is also called the envelope sender, bounce address, or MAIL FROM address.

The Return-Path is part of the SMTP specification in [RFC 5321](https://datatracker.ietf.org/doc/html/rfc5321) and the message format in [RFC 5322](https://datatracker.ietf.org/doc/html/rfc5322).

## Why Return-Path matters

The Return-Path serves two critical functions in email delivery:

### Bounce handling

When a message cannot be delivered, the receiving server sends a bounce message (a delivery status notification) to the Return-Path address. Without a valid Return-Path, bounces go nowhere, and the sender never learns about delivery failures.

Bounce messages are important for list hygiene.[^verp] If you send mail to an address that no longer exists, the bounce tells you to stop sending to that address. Sending to invalid addresses repeatedly damages your sender reputation.

### SPF alignment

The Return-Path domain is the domain that <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> checks. The <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> alignment check compares the Return-Path domain with the visible From domain. If they do not match (in relaxed mode, at the organizational domain level), the message fails DMARC alignment for SPF.

## How Return-Path works

### The envelope vs. the header

The Return-Path exists in two places:

1. **The SMTP envelope**: The `MAIL FROM` command sets the envelope sender address. This address is not visible to the recipient. It is used for bounce delivery and SPF checks.
1. **The Return-Path header**: The receiving mail server adds a `Return-Path` header to the message when it accepts the message. The header contains the envelope sender address from the `MAIL FROM` command.

The sender does not set the `Return-Path` header. The receiving server adds it.[^null-sender] The sender only sets the envelope sender through the `MAIL FROM` command.

### Example

A message might have these fields:

```text
MAIL FROM: <bounce+019a8c26@mail.example.com>   (envelope sender)
From: billing@example.com                             (visible header)
Return-Path: bounce+019a8c26@mail.example.com   (added by receiver)
```

The recipient sees `billing@example.com` in the mail client. Bounce messages go to the tagged address. The <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> check uses `mail.example.com`.

### Bounce address tag verification (BATV)

Some senders use BATV (Bounce Address Tag Verification) to detect bounce forgery. BATV adds a cryptographic tag to the envelope sender address. When a bounce comes back, the sender verifies the tag. If the tag is missing or invalid, the bounce is forged and is discarded.

BATV is defined in [IETF draft draft-levine-smtp-batv](https://datatracker.ietf.org/doc/html/draft-levine-smtp-batv).[^batv-status]

## DNS configuration

The sender domain has MX and SPF records. The MX record routes bounce messages to the platform. The SPF record authorizes the sending servers.

The built-in nameserver serves these records. You do not need a separate Return-Path domain or DNS record.

## How the platform uses Return-Path

The platform sets the envelope sender (the `MAIL FROM` address) to a subdomain of your sender domain. The format is:

```text
bounce+<message-id>@mail.<your-domain>
```

The tag after `bounce+` contains the outgoing message ID. The sender domain routes bounce messages to the platform's MX service.

The Return-Path domain is part of the <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> setup. The envelope sender domain must align with the visible From domain for <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>. The platform uses a subdomain, which aligns under relaxed DMARC.

## Further reading

- [RFC 5321: Simple Mail Transfer Protocol (Section 4.4: Trace information)](https://datatracker.ietf.org/doc/html/rfc5321#section-4.4)
- [RFC 5322: Internet Message Format (Section 3.6.7: Return-Path)](https://datatracker.ietf.org/doc/html/rfc5322#section-3.6.7)
- [RFC 3464: An Extensible Message Format for Delivery Status Notifications](https://datatracker.ietf.org/doc/html/rfc3464)
- <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>: Sender Policy Framework
- <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>: Domain-based Message Authentication, Reporting, and Conformance
- <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a>: Simple Mail Transfer Protocol

[^terminology]: The terms "Return-Path", "envelope sender", "bounce address", and "MAIL FROM address" all refer to the same concept in different contexts. "MAIL FROM" is the SMTP command. "Return-Path" is the header added by the receiving server. "Envelope sender" and "bounce address" are operational terms.

[^verp]: Variable Envelope Return Path (VERP) encodes the recipient address in the envelope sender. For example, a message to `alice@example.com` gets the envelope sender `list-bounce-alice=example.com@sender.com`. When a bounce comes back, the sender can identify the exact recipient without parsing the bounce message body.

[^null-sender]: Bounce messages themselves use a null envelope sender (`MAIL FROM:<>`). This empty address prevents bounce loops: a bounce to a bounce would also use `<>`, and most servers drop messages with a null sender as the recipient.

[^batv-status]: BATV is an IETF draft, not a published RFC. It is not a standard, but the technique is widely used by mailing list operators to prevent bounce forgery.
