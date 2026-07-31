# MX

MX (Mail Exchange) is a DNS record that tells senders which mail server receives email for a domain. Each MX record has a priority value and a mail server hostname.

## How MX works

When someone sends an email to `user@example.com`, the sending mail server looks up the MX records for `example.com`. The sender connects to the MX host with the lowest priority number first. If that server is unavailable, it tries the next one.

## MX record format

An MX record has two parts:

- **Priority** — a number. Lower numbers mean higher priority.
- **Hostname** — the fully qualified domain name of the mail server.

For example, `10 mail.example.com` means the mail server `mail.example.com` has priority 10.

## How relay uses MX

For incoming mail, relay points the MX record of your receiving domain to your sender subdomain. For example, `MX app.example.com → mail.relay.example.com`. The relay MX server receives the mail and dispatches it to your webhooks.

For outgoing mail, relay uses the \[SMTP\]({% url 'know_how:detail' slug='smtp' %}) server on port 587. The MX record is only for incoming mail.
