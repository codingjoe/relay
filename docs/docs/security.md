---
name: Security
description: How relay protects your account, your credentials, and your webhook deliveries
author: Johannes Maron
---

# Security

> **TL;DR**: relay signs you in with GitHub OAuth and stores no passwords. relay encrypts every signing key at rest and signs every webhook delivery. This page explains each protection.

## Account security

relay uses GitHub OAuth for sign-in. relay never sees or stores a password. GitHub authenticates you, and relay creates your account and organization on your first sign-in.

Every account belongs to an organization. An organization owns its domains, credentials, and messages. relay isolates organizations from each other. Members of one organization cannot read the data of another organization.

## Credential security

Your application submits email with an SMTP credential. A credential belongs to one organization only. You can create new credentials and delete old ones in the dashboard at any time. When you delete a credential, relay rejects every submission that uses it.

## Signing key security

relay signs every outgoing message with DKIM. The private key of a DKIM signature must stay secret. relay encrypts each private key with Fernet before it stores the key. Only the public keys appear in DNS. An attacker who steals the database cannot sign messages for your domain.

## Webhook security

relay delivers incoming email to your webhook over HTTPS. Every delivery includes three headers: `webhook-id`, `webhook-timestamp`, and `webhook-signature`. relay signs each delivery with an Ed25519 key that belongs to that webhook alone. Your application verifies the signature with the webhook public key in `whpk_` format. Any Standard Webhooks SDK can do this check for you.

## Related pages

- <a href="{% url 'docs:detail' slug='encryption' %}">Encryption</a>. How relay protects messages in transit and key material at rest.
- <a href="{% url 'docs:detail' slug='data-privacy' %}">Data privacy</a>. Where relay stores your data and how long relay keeps it.
- <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>. What a DKIM signature is and how a verifier checks it.
