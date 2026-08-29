---
name: Encryption
description: How relay encrypts messages in transit and protects key material at rest
author: Johannes Maron
---

# Encryption

> **TL;DR**: Your messages travel over TLS on every connection. relay enforces MTA-STS for recipient domains that publish a policy. relay encrypts every DKIM private key at rest.

## Submission: your application to relay

Your application submits outgoing email over an encrypted connection. Port 465 uses implicit TLS. Port 587 uses STARTTLS, and relay accepts no message before STARTTLS. relay accepts no plaintext submission.

## Delivery: relay to the recipient

relay delivers your message to the recipient mail server with STARTTLS on port 25. Some recipient domains publish an MTA-STS policy. For those domains, relay downloads the policy and delivers only to hosts that the policy permits. A network attacker cannot force the connection back to plaintext for these domains.

## Inbound: remote senders to relay

Remote mail servers deliver incoming email to the relay MX server with STARTTLS on port 25. relay publishes an MTA-STS policy for every managed domain. The policy tells senders to use TLS and lists the valid hosts. relay also collects TLS-RPT reports and shows TLS failures in the dashboard.

## Key material at rest

relay encrypts every DKIM private key with Fernet before storage. Only the public keys appear in DNS. See <a href="{% url 'docs:detail' slug='security' %}">Security</a> for the details.

## Message storage

relay stores each raw message body in S3-compatible object storage in the EU. relay stores the message metadata in PostgreSQL. relay keeps a raw body only as long as delivery requires it. See the <a href="{% url 'legal:privacy' %}">privacy policy</a> for the retention periods.

## What relay does not encrypt

Email is a store-and-forward system. relay cannot encrypt message content end to end, because every mail server on the path must read the message. If you need end-to-end confidentiality, encrypt the content in your application before you submit it.
