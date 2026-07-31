# MTA-STS

MTA-STS (SMTP MTA Strict Transport Security) is a standard that tells sending mail servers to use TLS when they connect to your mail server. It prevents downgrade attacks and man-in-the-middle interception of inbound mail.

## How MTA-STS works

Sending mail servers look up the MTA-STS DNS record. The record points to a policy file served over HTTPS. The policy file specifies the TLS mode and which MX hosts are valid. Senders cache the policy and refuse to deliver over an unencrypted connection when the mode is `enforce`.

## DNS records

MTA-STS uses two DNS records:

- `_mta-sts.<domain>` (TXT) — contains a policy ID tag `id=`. When you change the policy, you update this ID.
- `mta-sts.<domain>` (CNAME) — points to the host that serves the policy file over HTTPS.

## Policy modes

The policy file specifies a `mode` tag with one of three values:

- `testing` — collect failures but do not enforce TLS.
- `enforce` — refuse to deliver over unencrypted connections.
- `none` — disable the policy.

## How relay uses MTA-STS

relay serves the MTA-STS policy file and the DNS records automatically. You add the TXT and CNAME records at your DNS provider. relay handles the rest.

## Related

MTA-STS works with \[TLS-RPT\]({% url 'know_how:detail' slug='tls-rpt' %}). TLS-RPT sends reports about TLS connection failures so you can monitor delivery problems.
