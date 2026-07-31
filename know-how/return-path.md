# Return-Path

The Return-Path is the email address that receives bounce messages and delivery status notifications. It is also called the envelope sender or bounce address.

## How Return-Path works

The SMTP envelope contains a MAIL FROM address. This address is not the same as the visible From header in the email. When a message bounces, the receiving server sends the bounce notification to the Return-Path address.

## DNS configuration

The Return-Path subdomain uses a CNAME record. The CNAME points from `rp.<domain>` to the relay Return-Path host. This lets relay receive and process bounce messages.

## How relay uses Return-Path

relay sets the Return-Path to a subdomain of your sender domain. The CNAME record points to the relay server. relay processes bounces and updates the delivery status. You do not need to configure the Return-Path manually.

## Related

The Return-Path domain is part of the \[SPF\]({% url 'know_how:detail' slug='spf' %}) setup. The envelope sender domain must match the SPF record for \[DMARC\]({% url 'know_how:detail' slug='dmarc' %}) alignment to pass.
