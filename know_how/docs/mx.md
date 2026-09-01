---
name: MX
description: Mail exchange records for domain email routing
author: Johannes Maron
---

# MX

> **TL;DR**: MX records tell senders which mail server receives email for a domain.

## What is MX?

MX (Mail Exchange) is a DNS record type that specifies the mail server responsible for receiving email for a domain. Each MX record has a priority value and a mail server hostname. When someone sends an email to a domain, the sending mail server looks up the MX records to find where to deliver the message.

MX records are part of the DNS specification in [RFC 1035][rfc-1035] and are used by SMTP as defined in [RFC 5321][rfc-5321].

## Why MX matters

Without an MX record, a sending mail server does not know where to deliver email for your domain. Some servers fall back to the A record of the domain, but this is not reliable. The MX record is the standard way to route email.

The MX record also enables load balancing and redundancy. You can list multiple MX records with different priorities. The sending server tries the highest-priority server first. If that server is unavailable, it tries the next one.

## How MX works

The MX lookup and delivery process follows these steps:

1. The sending mail server needs to deliver a message to `user@example.com`.
1. The server queries DNS for the MX records of `example.com`.
1. DNS returns a list of MX records, each with a priority and a hostname.
1. The sending server sorts the records by priority (lowest number first).
1. The server connects to the first MX host on <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a> port 25.
1. If the connection fails, the server tries the next MX host in the sorted list.
1. If all MX hosts fail, the server queues the message for later retry.[^retry-behavior]

### Priority values

The priority value is a 16-bit integer (0 to 65535). Lower numbers mean higher priority. For example:

```text
example.com.  MX  10  mail1.example.com.
example.com.  MX  20  mail2.example.com.
```

In this example, `mail1` has priority 10 and `mail2` has priority 20. Senders try `mail1` first. If `mail1` is unavailable, they try `mail2`.

When two MX records have the same priority, senders pick one at random.[^equal-priority] This distributes load across the two servers.

### The fallback to A records

If a domain has no MX records, some sending servers try to deliver to the A record of the domain itself. This behavior is defined in [RFC 5321][rfc-5321] Section 5.1.[^a-record-fallback] However, this fallback is not universal. Many modern mail servers do not fall back to A records. You should always publish an explicit MX record.

## How to set up MX

1. Decide which server receives messages for your domain.
1. Publish an MX record that points to that server.
1. Use priority 10 for the primary server.
1. Add a backup server with a higher priority value for redundancy.

The MX record routes incoming deliveries only. Outgoing submissions use a separate <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a> server and do not use the MX record.

## Further reading

- [RFC 1035][rfc-1035]: Domain Names: Implementation and Specification
- [RFC 5321][rfc-5321]: Simple Mail Transfer Protocol (Section 5: MX lookup)
- <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a>: Simple Mail Transfer Protocol
- <a href="{% url 'know_how:detail' slug='ptr' %}">PTR</a>: Pointer records (reverse DNS)

[^retry-behavior]: The retry schedule is implementation-specific. [RFC 5321][rfc-5321] recommends at least 4 to 5 days of retries. The sending server typically waits longer between each retry attempt (for example, 15 minutes, 1 hour, 4 hours, 8 hours).

[^equal-priority]: The random selection for equal-priority MX records is defined in [RFC 5321][rfc-5321] Section 5.1. The term "equal preference" means the sender can try any of the servers at that priority level in any order.

[^a-record-fallback]: The A record fallback is a legacy behavior from the original SMTP specification (RFC 821, 1982). Modern mail servers may still implement it, but it is unreliable. A domain without an MX record is often misconfigured or abandoned.

[rfc-1035]: https://www.rfc-editor.org/info/rfc1035/
[rfc-5321]: https://www.rfc-editor.org/info/rfc5321/
