# Email Service Instructions

Apply these rules to `services/email/`.

## Dependencies

Shared modules (`mta_sts`, `proxy_protocol`, `spam`, `tls`) depend on no
first-party app.

## Primary keys

`Message` and `Transmission` use UUIDv7 because their IDs are SMTP message
IDs. Models with a foreign key to a message model also use UUIDv7.
`abstract.W001` enforces this.

## Task queues

Use `ingress` for received mail, `egress` for outgoing submissions,
`delivery` for SMTP delivery, and `default` for everything else.

## Naming

Email abbreviations are OK: SPF, DKIM, DMARC, MX, SMTP, PTR.
