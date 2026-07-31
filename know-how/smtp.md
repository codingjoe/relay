# SMTP

SMTP (Simple Mail Transfer Protocol) is the standard protocol for sending email between mail servers. relay uses SMTP for outgoing mail submissions on port 587.

## How SMTP works

A mail client connects to the SMTP server and authenticates with a username and password. The client sends the message envelope (sender and recipient addresses) and the message body. The SMTP server then delivers the message to the recipient mail server.

## Submission vs. relay

SMTP has two common roles:

- **Submission** — a client sends a message to a mail server for delivery. This uses port 587 with STARTTLS.
- **Relay** — a mail server forwards a message to another mail server. This uses port 25.

relay accepts submissions on port 587. The relay SMTP server authenticates each request with an API key. The server then delivers the message to the recipient.

## STARTTLS

STARTTLS upgrades a plain-text connection to an encrypted TLS connection. The client and server start with a plain-text handshake. Then they negotiate TLS encryption before any credentials are sent.

## How relay uses SMTP

relay provides an API key for each organization. You use this key as the SMTP password. The SMTP server stores the raw message body and dispatches delivery through the Django task framework.
