---
name: ARC
description: Sealed authentication results for forwarded mail
author: Johannes Maron
---

# ARC

> **TL;DR**: ARC lets a mail intermediary seal its authentication results into a message. The final receiver can verify what every hop on the forwarding path saw.

## What is ARC?

ARC (Authenticated Received Chain) is an email standard that lets an intermediary attach its authentication assessment to a message and sign it. As a message travels through forwarders and mailing lists, each ARC-enabled intermediary adds its own sealed assessment. The final receiver can see who handled the message and what the authentication results were at each hop.

ARC is defined in [RFC 8617](https://datatracker.ietf.org/doc/html/rfc8617).[^experimental]

## Why ARC matters

Intermediaries break email authentication. A forwarder re-envelopes the message: it submits the message with its own envelope sender, so <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a> no longer matches the original domain. Intermediaries also modify the message: mailing lists add footers, subject tags, and new headers, which breaks <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a> signatures.

By the time the message reaches its final destination, <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> may fail even though the message was legitimate when it was sent. The sender has no way to prove that the message authenticated at the start of its journey.

ARC solves this problem. An ARC-enabled intermediary records the authentication results it computed while receiving the message, and seals them. The sealed results travel with the message, so the final receiver can base its decision on the state at the point of sealing instead of the broken state at final delivery.

## How ARC works

Each ARC-enabled intermediary adds one ARC set to the message. An ARC set is three headers:

| Header                       | Purpose                                                      |
| ---------------------------- | ------------------------------------------------------------ |
| `ARC-Authentication-Results` | The intermediary's SPF, DKIM, and DMARC results              |
| `ARC-Message-Signature`      | A DKIM-style signature over the message headers and body     |
| `ARC-Seal`                   | A signature over the set's own headers and all earlier seals |

The `i=` tag numbers each set. The first intermediary seals with `i=1`, the next with `i=2`, and so on. One set is added per hop, and the sets together form the chain of custody.

The `cv=` tag in the ARC-Seal records the validation status of the chain up to that seal. `none` means no prior chain existed when the message was sealed. `pass` means the prior chain validated. `fail` means the prior chain did not validate, for example because the message changed after an earlier seal.

## How to verify an ARC seal

Verifying a seal works like verifying <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>. The ARC-Seal header carries the selector `s=` and the signing domain `d=` of the sealing intermediary. Look up the public key in DNS at `<selector>._domainkey.<domain>`, and check the signatures of each set in chain order. The newest seal's `cv=` tag gives the status of the entire chain.

## Limits and trust

ARC reports authentication results, it does not force acceptance. A receiver that trusts the sealing domain can use a sealed pass to accept mail that would otherwise fail DMARC. A receiver that does not trust the sealing domain can ignore the chain and apply its own policy. ARC deliberately leaves this decision to the receiver.

A broken chain means the message changed after a seal was applied. It does not tell you who changed it or why, only that at least one seal no longer covers the message as received.

## Further reading

- [RFC 8617: The Authenticated Received Chain (ARC) Protocol](https://datatracker.ietf.org/doc/html/rfc8617)
- [RFC 8617 Section 4.4: Chain Validation Status](https://datatracker.ietf.org/doc/html/rfc8617#section-4.4)
- <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>: DomainKeys Identified Mail
- <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>: Sender Policy Framework
- <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>: Domain-based Message Authentication, Reporting, and Conformance

[^experimental]: RFC 8617 has the status "Experimental". Unlike DKIM ([RFC 6376](https://datatracker.ietf.org/doc/html/rfc6376)), it has not completed the full IETF standards process. It is nonetheless deployed by major mailbox providers.
