---
name: PTR
description: Reverse DNS lookup for IP verification
author: Johannes Maron
---

# PTR

> **TL;DR**: A PTR record maps an IP address back to a hostname. Mail servers use it to verify the sending server.

## What is PTR?

A PTR (Pointer) record is a DNS record that performs a reverse lookup. It maps an IP address to a hostname. This is the opposite of an A record, which maps a hostname to an IP address.

PTR records are part of the DNS specification in [RFC 1035](https://datatracker.ietf.org/doc/html/rfc1035).

## Why PTR matters

Many receiving mail servers check the PTR record of the sending IP address as part of their spam filtering. If the PTR hostname does not match the sending domain, or if no PTR record exists, the receiving server may reject the message or flag it as spam.

Major email providers like Gmail and Microsoft 365 use the PTR check as a strong signal. A missing or mismatched PTR record is one of the most common reasons for legitimate email to land in the spam folder.

The PTR check also helps prevent spam because most spam comes from compromised servers and botnets. These sources usually do not have valid PTR records.

## How PTR works

### IPv4 reverse DNS

For IPv4, PTR records live in the `in-addr.arpa` zone. The IP address is reversed and appended to `in-addr.arpa`. For example, the IP address `192.0.2.1` has a PTR record at:

```text
1.2.0.192.in-addr.arpa.  PTR  mail.example.com.
```

### IPv6 reverse DNS

For IPv6, PTR records live in the `ip6.arpa` zone.[^ipv6-ptr] The IPv6 address is expanded to its full hexadecimal form, reversed nibble by nibble, and appended to `ip6.arpa`. For example, the IPv6 address `2001:db8::1` has a PTR record at:

```text
1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa.  PTR  mail.example.com.
```

### Forward-confirmed reverse DNS (FCrDNS)

A common verification technique is forward-confirmed reverse DNS (FCrDNS). The receiving server performs two lookups. First it looks up the PTR record for the sending IP address, which returns a hostname. Then it looks up the A or AAAA record for that hostname, which must return the original IP address.

If both lookups match, the IP address has valid forward-confirmed reverse DNS.[^fcrdns-weakness] This check prevents a sender from publishing an arbitrary hostname in their PTR record.

### Who controls PTR records

PTR records are controlled by the organization that owns the IP address range.[^ptr-ownership] This is usually the internet service provider (ISP) or the cloud hosting provider. You cannot set a PTR record in your domain's DNS zone. You must ask your ISP or hosting provider to set it for you.

This is different from most other DNS records (A, MX, TXT), which you control through your DNS provider.

## How to set up PTR

PTR records are controlled by the owner of the IP address range. This is usually the internet service provider (ISP) or cloud hosting provider. You cannot set a PTR record in your domain's DNS zone.

1. Ask your provider to set a PTR record for the sending IP address.
1. Use a hostname that resolves back to the same IP address.

The hostname must match the sending domain so that the PTR record passes the FCrDNS check.

## Further reading

- [RFC 1035: Domain Names: Implementation and Specification (Section 3.5: PTR)](https://datatracker.ietf.org/doc/html/rfc1035#section-3.5)
- [RFC 1912: Common DNS Operational and Configuration Errors (Section 2.1: PTR)](https://datatracker.ietf.org/doc/html/rfc1912#section-2.1)
- <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a>: Simple Mail Transfer Protocol
- <a href="{% url 'know_how:detail' slug='mx' %}">MX</a>: Mail Exchange records

[^ipv6-ptr]: IPv6 reverse DNS is often neglected. Many organizations set up IPv4 PTR records but forget IPv6. This causes delivery problems when the receiving server connects over IPv6 and the PTR check fails. Set up PTR records for both IPv4 and IPv6.

[^fcrdns-weakness]: FCrDNS is a weak authentication check. An attacker who controls both the forward and reverse DNS zones for an IP address can set up valid FCrDNS. The check is useful as a spam signal, not as a security boundary.

[^ptr-ownership]: The PTR record for an IP address is published in the reverse DNS zone. This zone is delegated to the IP address owner, not the domain owner. For cloud servers, the hosting provider (for example, AWS, GCP, or Hetzner) usually provides a control panel or API to set the PTR record.
