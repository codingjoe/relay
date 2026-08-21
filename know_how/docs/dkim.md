---
name: DKIM
description: Cryptographic signature for outgoing email
author: Johannes Maron
---

# DKIM

> **TL;DR**: DKIM adds a cryptographic signature to each outgoing email. Receiving servers verify the signature with a public key from DNS. The platform generates and manages all keys for you.

## What is DKIM?

DKIM (DomainKeys Identified Mail) is an email authentication standard that adds a digital signature to outgoing messages. The signature proves that the message came from the signing domain and that the message content was not changed in transit.

DKIM is defined in [RFC 6376](https://datatracker.ietf.org/doc/html/rfc6376). It is an Internet Standard, which means it has passed the highest level of IETF review.[^internet-standard]

## Why DKIM matters

SPF verifies the sending IP address, but it cannot verify the message content. A message can pass SPF and still be modified in transit. DKIM solves this problem with cryptographic signatures.

DKIM provides two guarantees that SPF cannot:

1. **Content integrity**: The signature covers selected message headers and the message body. If an attacker changes the content, the signature verification fails.
1. **Domain accountability**: The signature identifies the domain that signed the message. This domain does not have to be the same as the visible From domain, but <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> alignment checks that they match.

DKIM is one of the two authentication methods that <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> uses. The other is <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>. DMARC requires at least one of the two to pass.

## How DKIM works

The DKIM signing and verification process has two sides:

### Signing (sending server)

1. The sending mail server generates a hash of selected message headers and the message body.
1. The server signs the hash with a private key.
1. The server adds a `DKIM-Signature` header to the message. This header contains the signature, the selector name, the signing algorithm, and the list of headers that were signed.

### Verification (receiving server)

1. The receiving server extracts the selector and signing domain from the `DKIM-Signature` header.
1. The server looks up the public key in DNS at `<selector>._domainkey.<domain>`.
1. The server computes a hash of the same headers and body.
1. The server verifies the signature with the public key.
1. If the verification succeeds, the message passes DKIM. If it fails, the message is tampered with or the key is invalid.

### The selector

The selector is a label that identifies which key to use. A domain can have multiple DKIM keys, each with a different selector. This design lets you rotate keys without downtime.[^key-rotation] You publish the new key under a new selector, update the signing configuration, and then remove the old key.

For example, `mail._domainkey.example.com` contains the public key for the `mail` selector.

### Body and header hashing

DKIM signs a selected set of headers, not the entire message. The `DKIM-Signature` header lists which headers are signed (the `h=` tag). Common headers to sign include `From`, `Subject`, `Date`, `Message-ID`, and `Reply-To`.

The body hash (the `bh=` tag) covers the message body. If any byte of the body changes in transit, the body hash does not match, and verification fails.[^body-length]

### Canonicalization

Email messages can be modified in transit by mailing list software, forwarders, or other mail servers. These modifications can add or remove whitespace, change line endings, or wrap long lines. DKIM uses canonicalization algorithms to handle minor changes:

- **Simple canonicalization**: Tolerates almost no changes. Any modification to the body or headers fails verification.
- **Relaxed canonicalization**: Tolerates minor whitespace and line-ending changes. This mode is more common because it allows messages to pass through most mail infrastructure without breaking the signature.

The canonicalization mode is specified in the `c=` tag of the `DKIM-Signature` header.

## DNS records

DKIM uses TXT records at `<selector>._domainkey.<domain>`. The record contains:

| Tag | Purpose             | Example                                        |
| --- | ------------------- | ---------------------------------------------- |
| `v` | Version             | `v=DKIM1`                                      |
| `k` | Key type            | `k=rsa` or `k=ed25519`                         |
| `p` | Public key (base64) | `p=MIIBIjANBgkqhkiG...`                        |
| `s` | Service type        | `s=email`                                      |
| `t` | Flags               | `t=s` (strict, subdomains cannot use this key) |

## Key types

DKIM supports several key types:

- **RSA-2048**: The most common key type. It provides strong security and is compatible with all receiving servers.
- **RSA-1024**: An older key size. Some receivers no longer accept RSA-1024 keys because the security margin is too small.
- **Ed25519**: A modern elliptic curve algorithm. It provides the same security as RSA-2048 with a much smaller key size.[^ed25519-support] Not all receiving servers support Ed25519 yet.

The platform supports all three key types. Each key type gets its own selector and DNS record.

## How the platform uses DKIM

The platform generates and stores the private keys for you. The keys live in the `kms` app, which manages key creation, storage, and signing. The platform publishes the public keys as DNS records on the sender subdomain through the built-in nameserver.

Each cipher type gets its own selector and CNAME record. You add the CNAME records at your DNS provider. The platform handles the rest, including key rotation.

## Further reading

- [RFC 6376: DomainKeys Identified Mail (DKIM) Signatures](https://datatracker.ietf.org/doc/html/rfc6376)
- [RFC 6376 Section 3.5: The DKIM-Signature header](https://datatracker.ietf.org/doc/html/rfc6376#section-3.5)
- [RFC 8301: DKIM Update](https://datatracker.ietf.org/doc/html/rfc8301)
- <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>: Domain-based Message Authentication, Reporting, and Conformance
- <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>: Sender Policy Framework

[^internet-standard]: RFC 6376 has the status "Internet Standard" (STD 76). This is the highest maturity level in the IETF standards process. It means the protocol is stable, widely implemented, and has significant operational experience.

[^key-rotation]: Key rotation is a security best practice. Rotate DKIM keys at least every 6 to 12 months. The platform handles key rotation for you. You do not need to manage the rotation schedule.

[^body-length]: The `l=` tag in the `DKIM-Signature` header limits the body hash to a specific number of bytes. This tag is rarely used and creates a security risk because an attacker can append content after the signed portion. Most implementations omit the `l=` tag entirely. See [RFC 6376 Section 5.4](https://datatracker.ietf.org/doc/html/rfc6376#section-5.4) for details.

[^ed25519-support]: Ed25519 support was added in [RFC 8463](https://datatracker.ietf.org/doc/html/rfc8463). Adoption is growing but not universal. The platform publishes Ed25519 keys alongside RSA keys, so receivers that support Ed25519 can use the smaller signature.
