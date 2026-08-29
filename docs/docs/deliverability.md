---
name: Deliverability
description: How relay gets your messages into the inbox
author: Johannes Maron
---

# Deliverability

> **TL;DR**: relay manages your DNS, signs every message with DKIM, and handles bounces for you. You write the message, and relay does the rest.

## Managed DNS

relay runs an authoritative nameserver for your domains. You delegate your domain with NS records and add one DMARC record. relay serves the MX, SPF, DKIM, and Return-Path records automatically. There is no zone file to edit and no record list to copy.

## A sender domain from the first minute

Every organization gets a managed sender domain at signup, for example `acme.open.example.com`. This domain is verified and DKIM-signed before you send your first message. You can send email immediately, with no DNS setup.

## Authentication on every message

relay signs every outgoing message with DKIM. The message gets a signature for every key algorithm of the domain, with RSA and Ed25519 keys. The envelope sender lives on your sender subdomain, so SPF passes too. If these terms are new to you, the know-how articles on <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>, <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>, and <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> explain each one.

## Bounce handling

Every outgoing message has a unique Return-Path address. When a recipient server rejects a message permanently, relay records the bounce and adds the address to the suppression list. relay does not send another message to a suppressed address. You can view the suppression list in the dashboard.

## Spam control before delivery

relay scans every outgoing message with rspamd before it leaves the platform. relay holds a message that looks like spam and records the spam score in the dashboard. A held message does not reach your recipients.

## Monitoring

The dashboard shows the status of every message and the SMTP transcript of every delivery attempt. It also shows DMARC aggregate and forensic reports, TLS-RPT reports, and bounce rates. You see problems early, so you can correct them before they hurt your deliverability.
