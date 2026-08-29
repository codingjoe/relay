---
name: Sender reputation
description: How relay builds and protects your sender reputation
author: Johannes Maron
---

# Sender reputation

> **TL;DR**: Your reputation is tied to your own domain. relay keeps your authentication aligned, stops sends to bounced addresses, and shows you the reports from mailbox providers.

## Your domain, your reputation

Every organization sends from its own domain. Mailbox providers track your domain through DKIM and DMARC. Your reputation reflects your own sending behavior, separately from other relay customers.

## Attribution on every message

relay signs every outgoing message with a DKIM key for your domain. Mailbox providers attribute the message to your domain, not to the relay platform. The envelope sender lives on your sender subdomain, so SPF and DKIM work together on every send.

## No sends to dead addresses

A high bounce rate damages a domain quickly. When a recipient server rejects a message permanently, relay adds the address to the suppression list. relay then stops all sends to that address. This keeps your bounce rate low.

## Spam-free output

Mailbox providers penalize domains that send spam. relay scans all outgoing mail with rspamd and holds suspicious messages before they leave. Your domain sends only clean mail.

## Reports you can use

Mailbox providers send aggregate DMARC reports for your domain every day. relay collects these reports, parses them, and shows you who sends as your domain. You can find misconfigured senders and spoofing attempts early. Forensic DMARC reports and TLS-RPT reports add detail on failures. See <a href="{% url 'docs:detail' slug='deliverability' %}">Deliverability</a> for the full monitoring story.

## Consistent infrastructure

The relay SMTP servers send with a hostname that matches their PTR records. Forward and reverse DNS agree, which is a common requirement of mailbox providers. Managed sender domains inherit this setup automatically.
