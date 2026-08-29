---
name: Data privacy
description: Where relay stores your data, how long relay keeps it, and what relay never stores
author: Johannes Maron
---

# Data privacy

> **TL;DR**: relay runs in the EU and transfers no data to third countries. relay hashes suppressed addresses, keeps bodies only for delivery, and sends no message content to error monitoring.

## EU hosting

relay runs on servers in the EU. Your data does not leave the EU. relay transfers no data to third countries.

## What relay stores, and for how long

relay stores message metadata in PostgreSQL and raw message bodies in S3-compatible object storage in the EU. relay keeps a raw body only as long as delivery requires it, and deletes it after successful delivery. Message metadata stays for 30 days. See the <a href="{% url 'legal:privacy' %}">privacy policy</a> for the full details.

## What relay never stores or sends

- The suppression list stores a salted SHA-256 hash of each address. relay never stores the plain address.
- Webhook payloads carry event data and a storage URL. The raw body is never part of the payload.
- Error monitoring receives no message bodies, tokens, or credentials.

## Data with a purpose

relay processes your data only to deliver messages and to show you reports. relay does not profile you, does not mine your data, and does not sell it.

## GDPR

relay complies with the GDPR. The <a href="{% url 'legal:privacy' %}">privacy policy</a> and the <a href="{% url 'legal:terms' %}">terms of service</a> contain the legal details.
