# SPF

SPF (Sender Policy Framework) is a DNS record that lists the mail servers authorized to send email for your domain. Receiving mail servers check the SPF record to verify the sender.

## How SPF works

When a mail server receives a message, it checks the SPF record of the envelope sender domain. The SPF record lists IP addresses and mechanisms that identify approved senders. If the sending IP matches the record, the message passes SPF.

## SPF record format

An SPF record is a TXT record that starts with `v=spf1`. It contains mechanisms separated by spaces:

- `a` — allow the IP addresses of the domain A records.
- `mx` — allow the IP addresses of the domain MX records.
- `ip4:x.x.x.x` — allow a specific IPv4 address.
- `ip6:xxxx` — allow a specific IPv6 address.
- `include:example.com` — include the SPF record of another domain.
- `~all` — soft fail for all other senders.
- `-all` — hard fail for all other senders.

## How relay uses SPF

relay publishes the SPF record for you on the sender subdomain. The record includes the SMTP server IP addresses. You do not need to configure SPF manually.

## SPF and DMARC

SPF is one of the two authentication methods that \[DMARC\]({% url 'know_how:detail' slug='dmarc' %}) uses. The other is \[DKIM\]({% url 'know_how:detail' slug='dkim' %}). DMARC requires at least one of the two to pass.
