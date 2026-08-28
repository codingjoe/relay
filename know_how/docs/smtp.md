---
name: SMTP
description: Protocol for sending email between mail servers
author: Johannes Maron
---

# SMTP

> **TL;DR**: SMTP is the standard protocol for sending email between mail servers. Submission servers accept messages on port 587 with STARTTLS and require authentication.

## What is SMTP?

SMTP (Simple Mail Transfer Protocol) is the standard protocol for sending and relaying email across the internet. It defines the commands that a mail client sends to a mail server to submit a message, and the commands that mail servers exchange to deliver messages to each other.

SMTP is defined in [RFC 5321](https://datatracker.ietf.org/doc/html/rfc5321). The message format that SMTP carries is defined in [RFC 5322](https://datatracker.ietf.org/doc/html/rfc5322).

## Why SMTP matters

SMTP is the foundation of email delivery. Every email that travels across the internet uses SMTP. Without it, mail servers could not communicate with each other.

SMTP was designed in 1982[^rfc821] and has grown around it since. The core protocol is simple, and that simplicity is a strength. It also means SMTP on its own leaves three gaps. It does not verify who sent a message, which is what <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>, <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>, and <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a> handle. It starts in plain text, so STARTTLS and <a href="{% url 'know_how:detail' slug='mta-sts' %}">MTA-STS</a> add encryption. And it never looks at the message content, which is left to spam filters and DKIM signatures.

## How SMTP works

An SMTP transaction has three phases:

### 1. Connection and greeting

The client connects to the server on the SMTP port. The server responds with a `220` greeting that identifies the server. The client responds with `EHLO` (extended hello) or `HELO`.[^ehlo-vs-helo] The server replies with a list of supported extensions.

### 2. Envelope and data

The client sends these commands:

| Command     | Purpose                                                                                                    |
| ----------- | ---------------------------------------------------------------------------------------------------------- |
| `MAIL FROM` | The envelope sender address (the <a href="{% url 'know_how:detail' slug='return-path' %}">Return-Path</a>) |
| `RCPT TO`   | The recipient address (can be repeated for multiple recipients)                                            |
| `DATA`      | Start of the message body                                                                                  |

After the `DATA` command, the client sends the message headers and body. The message ends with a line that contains a single dot (`.`).

### 3. Termination

The client sends the `QUIT` command to close the connection. The server acknowledges and disconnects.

### SMTP response codes

The server responds to each command with a three-digit code:

| Code range | Meaning                                              |
| ---------- | ---------------------------------------------------- |
| `2xx`      | Success. The command completed                       |
| `3xx`      | Continue. The server expects more data               |
| `4xx`      | Temporary failure. The client should try again later |
| `5xx`      | Permanent failure. The client should not retry       |

A `4xx` response tells the client to queue the message and retry later.[^dsn-spec] A `5xx` response tells the client to give up and return a bounce to the sender.

## SMTP ports

SMTP uses different ports for different roles:

| Port | Purpose                                    | Encryption        |
| ---- | ------------------------------------------ | ----------------- |
| 25   | Server-to-server MX delivery               | Optional STARTTLS |
| 587  | Client-to-server submission                | STARTTLS          |
| 465  | Client-to-server submission (implicit TLS) | TLS               |

Port 25 is for mail server to mail server communication.[^port25-blocked] It is the port that <a href="{% url 'know_how:detail' slug='mx' %}">MX</a> records point to. Many ISPs block port 25 on residential connections to prevent spam.

Port 587 is for mail clients to submit messages to a mail server. It requires authentication and uses STARTTLS for encryption.

Port 465 is the legacy implicit TLS submission port. Some providers still use it, but port 587 is the standard.

## STARTTLS

STARTTLS is an SMTP extension that upgrades a plain-text connection to TLS. The process works as follows:

1. The client connects in plain text.
1. The server advertises STARTTLS support in the `EHLO` response.
1. The client sends the `STARTTLS` command.
1. The server responds with `220 Ready to start TLS`.
1. Both sides negotiate the TLS handshake.
1. The client sends `EHLO` again over the encrypted connection.
1. All subsequent commands, including authentication, are encrypted.

STARTTLS is opportunistic by default. If the server does not advertise STARTTLS, or if the TLS handshake fails, the client can fall back to plain text. <a href="{% url 'know_how:detail' slug='mta-sts' %}">MTA-STS</a> solves this problem by requiring TLS.

## How to submit mail

To submit a message to a submission server:

1. Connect to the server on port 587.
1. Upgrade the connection with STARTTLS.
1. Authenticate with your account credentials.
1. Send the message.

The server queues the message for delivery and reports the result back to the client. Submission servers require authentication so that they do not forward messages for unknown senders.

## Further reading

- [RFC 5321: Simple Mail Transfer Protocol](https://datatracker.ietf.org/doc/html/rfc5321)
- [RFC 5322: Internet Message Format](https://datatracker.ietf.org/doc/html/rfc5322)
- [RFC 3207: SMTP Service Extension for Secure SMTP over Transport Layer Security](https://datatracker.ietf.org/doc/html/rfc3207)
- <a href="{% url 'know_how:detail' slug='spf' %}">SPF</a>: Sender Policy Framework
- <a href="{% url 'know_how:detail' slug='dkim' %}">DKIM</a>: DomainKeys Identified Mail
- <a href="{% url 'know_how:detail' slug='dmarc' %}">DMARC</a>: Domain-based Message Authentication, Reporting, and Conformance
- <a href="{% url 'know_how:detail' slug='return-path' %}">Return-Path</a>: The bounce address and envelope sender

[^rfc821]: The original SMTP specification was [RFC 821](https://datatracker.ietf.org/doc/html/rfc821) (August 1982). It was obsoleted by [RFC 5321](https://datatracker.ietf.org/doc/html/rfc5321) in October 2008. The core command set is the same, but RFC 5321 added clarity, error handling, and security considerations.

[^ehlo-vs-helo]: `EHLO` was introduced in [RFC 1869](https://datatracker.ietf.org/doc/html/rfc1869) (SMTP Service Extensions). It lets the server advertise supported extensions. `HELO` is the original greeting from RFC 821 and does not support extensions. Modern clients should use `EHLO` and fall back to `HELO` only if the server rejects it.

[^dsn-spec]: Delivery Status Notifications (DSN) are defined in [RFC 3464](https://datatracker.ietf.org/doc/html/rfc3464). The bounce message format includes structured fields for the original recipient, the failure reason, and the diagnostic code.

[^port25-blocked]: Port 25 blocking by ISPs started in the late 1990s to combat spam from compromised home computers. This practice is now standard among most consumer ISPs. The blocking is one reason that authenticated submission on port 587 was introduced in [RFC 4409](https://datatracker.ietf.org/doc/html/rfc4409).
