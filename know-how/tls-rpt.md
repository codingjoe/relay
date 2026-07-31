# TLS-RPT

TLS-RPT (TLS Reporting) is a standard that lets mail servers send reports about TLS connection failures. It works with \[MTA-STS\]({% url 'know_how:detail' slug='mta-sts' %}) to help you monitor and fix delivery problems.

## How TLS-RPT works

When a sending mail server fails to establish a TLS connection to your mail server, it sends a report. The report contains the failed connection details and the reason for the failure. You receive these reports by email or HTTPS POST.

## DNS record

TLS-RPT uses a TXT record at `_smtp._tls.<domain>`. The record contains:

- `v=TLSRPTv1` — the protocol version.
- `rua=` — the destination for reports, either `mailto:` or `https:`.

## How relay uses TLS-RPT

relay collects TLS-RPT reports for you. You add the TXT record at your DNS provider. relay provides the reporting endpoint automatically. You can view the reports in the TLS reports dashboard.

## Related

TLS-RPT works with \[MTA-STS\]({% url 'know_how:detail' slug='mta-sts' %}). MTA-STS enforces TLS for incoming mail. TLS-RPT tells you when a sender cannot connect with TLS.
