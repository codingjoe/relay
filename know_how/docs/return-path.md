---
name: Return-Path
description: Bounce address for email delivery notifications
author: Johannes Maron
---

# Return-Path

> **TL;DR**: The Return-Path is the email address that receives bounce messages. It is set by the sending mail server and is separate from the visible From address.

## What is Return-Path?

The Return-Path is the email address that receives bounce messages and delivery status notifications.[^terminology] It is also called the envelope sender, bounce address, or MAIL FROM address.

The Return-Path is part of the SMTP specification in [RFC 5321](https://datatracker.ietf.org/doc/html/rfc5321) and the message format in [RFC 5322](https://datatracker.ietf.org/doc/html/rfc5322).

## Why Return-Path matters

The Return-Path does two important jobs in email delivery:

### Bounce handling

When a message cannot be delivered, the receiving server sends a bounce message (a delivery status notification) to the Return-Path address. Without a valid Return-Path, bounces go nowhere, and the sender never learns about delivery failures.

Bounce messages are important for list hygiene.[^verp] If you send mail to an address that no longer exists, the bounce tells you to stop sending to that address. Sending to invalid addresses repeatedly damages your sender reputation.

### SPF alignment

The Return-Path domain is the domain that <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> checks. The <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> alignment check compares the Return-Path domain with the visible From domain. If they do not match (in relaxed mode, at the organizational domain level), the message fails DMARC alignment for SPF.

## How Return-Path works

### The envelope vs. the header

The Return-Path shows up in two places. In the SMTP envelope, the `MAIL FROM` command sets the envelope sender address. The recipient never sees it, but it drives bounce delivery and SPF checks. Separately, the receiving mail server adds a `Return-Path` header to the accepted message. That header holds the same envelope sender address.

The sender does not set the `Return-Path` header. The receiving server adds it.[^null-sender] The sender only sets the envelope sender through the `MAIL FROM` command.

### Example

A message might have these fields:

```text
MAIL FROM: <bounce+019a8c26@bounces.example.com>   (envelope sender)
From: billing@example.com                           (visible header)
Return-Path: bounce+019a8c26@bounces.example.com   (added by receiver)
```

The recipient sees `billing@example.com` in the mail client. Bounce messages go to the tagged address. The <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> check uses `bounces.example.com`.

### Bounce address tag verification (BATV)

Some senders use BATV (Bounce Address Tag Verification) to detect bounce forgery. BATV adds a cryptographic tag to the envelope sender address. When a bounce comes back, the sender verifies the tag. If the tag is missing or invalid, the bounce is forged and is discarded.

BATV is defined in [IETF draft draft-levine-smtp-batv](https://datatracker.ietf.org/doc/html/draft-levine-smtp-batv).[^batv-status]

## DNS configuration

The bounce domain needs MX and SPF records. The MX record routes bounce messages back to the mail server. The SPF record authorizes the mail servers.

You do not need a separate DNS record for the Return-Path.

## How to set up the Return-Path

1. Choose a subdomain of your sending domain for the envelope sender, for example `bounces.example.com`.
1. Publish an MX record for the subdomain so that bounce messages return to your mail server.
1. Add the subdomain to your SPF record.
1. Make sure that the envelope sender domain aligns with the visible From domain for <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>.

A subdomain of the sending domain aligns under relaxed DMARC. Add a tag such as `bounce+<message-id>` to the local part to identify the original message from a bounce.

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
