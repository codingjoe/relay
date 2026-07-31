# DMARC

DMARC (Domain-based Message Authentication, Reporting, and Conformance) is an email authentication protocol. It tells receiving mail servers what to do when an email fails \[SPF\]({% url 'know_how:detail' slug='spf' %}) or \[DKIM\]({% url 'know_how:detail' slug='dkim' %}) checks.

DMARC uses the DNS record `_dmarc.<domain>`. The record contains a policy tag `p=` with one of three values:

- `none` — monitor only, deliver all mail.
- `quarantine` — send failing mail to the spam folder.
- `reject` — reject failing mail at the SMTP server.

## Alignment

DMARC checks that the domain in the visible From address matches the domain that \[SPF\]({% url 'know_how:detail' slug='spf' %}) or \[DKIM\]({% url 'know_how:detail' slug='dkim' %}) verified. This process is called alignment. Without alignment, a spammer can pass SPF on their own domain and spoof yours.

## Reports

DMARC can send two types of reports:

- **Aggregate reports (RUA)** — daily XML summaries of all mail that used your domain. These reports show which messages passed and which failed authentication.
- **Forensic reports (RUF)** — copies of individual failed messages. These reports help you identify the source of spoofing.

relay collects aggregate and forensic reports for you. You can view them in the DMARC reports dashboard in your organization.

## How relay uses DMARC

You set one DMARC record on your root domain. relay serves all other DNS records automatically. The DMARC record uses relaxed alignment, so it covers all subdomains.
