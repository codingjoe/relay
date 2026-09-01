---
name: TLS-RPT
description: Reports about TLS connection failures
author: Johannes Maron
---

# TLS-RPT

> **TL;DR**: TLS-RPT lets mail servers send you reports about TLS connection failures. It works with MTA-STS to help you monitor and fix delivery problems.

## What is TLS-RPT?

TLS-RPT (SMTP TLS Reporting) is a standard that lets sending mail servers send reports about TLS connection failures to the receiving domain. The reports contain details about failed connections, the reason for the failure, and the sending server that experienced the problem.

TLS-RPT is defined in [RFC 8460][rfc-8460].

## Why TLS-RPT matters

TLS encryption protects email in transit, but it can fail for many reasons:

- The receiving server has an expired or misconfigured TLS certificate.
- A network device blocks the `STARTTLS` command (a downgrade attack).
- The receiving server does not support TLS at all.
- The TLS version or cipher suite is too weak.

Without TLS-RPT, you have no visibility into these failures. Sending servers silently fall back to plain text or queue messages for later delivery. You only learn about the problem when recipients complain that they did not receive an email.

TLS-RPT gives you this visibility. Sending servers send you structured reports about every TLS failure.[^report-interval] You can use these reports to fix problems before they affect your users.

TLS-RPT works with <a href="{% url 'know_how:detail' slug='mta-sts' %}">MTA-STS</a>. MTA-STS enforces TLS for incoming mail. TLS-RPT tells you when a sender cannot connect with TLS.

## How TLS-RPT works

The TLS-RPT process has three steps:

1. The receiving domain publishes a TLS-RPT DNS record. The record tells senders where to send reports.
1. When a sending server fails to establish a TLS connection, it generates a report.
1. The sending server sends the report to the destination in the DNS record.

### The DNS record

TLS-RPT uses a TXT record at `_smtp._tls.<domain>`. The record contains:

| Tag   | Purpose            | Example                                                              |
| ----- | ------------------ | -------------------------------------------------------------------- |
| `v`   | Protocol version   | `v=TLSRPTv1`                                                         |
| `rua` | Report destination | `rua=mailto:tls@example.com` or `rua=https://example.com/tls-report` |

The `rua` destination can be an email address or an HTTPS URL.[^rua-transport] When the destination is an HTTPS URL, the sending server POSTs the report as a JSON document.

### Report format

TLS-RPT reports are JSON documents. Each report contains:

| Field               | Description                                         |
| ------------------- | --------------------------------------------------- |
| `organization-name` | The receiving domain name                           |
| `date-range`        | The reporting period (start and end timestamps)     |
| `contact-info`      | How to contact the report sender                    |
| `report-id`         | Unique report identifier                            |
| `policy`            | The TLS policy that was in effect (MTA-STS or none) |
| `summary`           | Count of successful and failed sessions             |
| `failure-details`   | Per-failure breakdown with reason and MX host       |

### Failure reasons

The report specifies one of these failure reasons:

- `starttls-not-supported`: The receiving server does not support STARTTLS.
- `certificate-host-mismatch`: The certificate hostname does not match the MX host.
- `certificate-expired`: The certificate has expired.
- `certificate-not-trusted`: The certificate is not issued by a trusted authority.
- `tls-version-unsupported`: The TLS version is too old or not supported.
- `cipher-suite-unsupported`: The cipher suite is not acceptable.[^failure-detail-optional]

## How to set up TLS-RPT

1. Publish a TXT record at `_smtp._tls.<domain>`.
1. Set the `rua` tag to the email address or HTTPS endpoint that receives the reports.
1. Configure the endpoint to collect and store the JSON reports.

The reports show which senders had TLS failures and the reason for each failure. Monitor the reports to find certificate and protocol issues before they affect your users.

## Further reading

- [RFC 8460][rfc-8460]: SMTP TLS Reporting
- [RFC 8460][rfc-8460] Section 4: Report format
- <a href="{% url 'know_how:detail' slug='mta-sts' %}">MTA-STS</a>: SMTP MTA Strict Transport Security
- <a href="{% url 'know_how:detail' slug='smtp' %}">SMTP</a>: Simple Mail Transfer Protocol

[^report-interval]: Reports are typically sent once per day per sending domain. The report covers all TLS connection attempts during that 24-hour period, both successful and failed.

[^rua-transport]: The HTTPS transport is preferred over email because it scales better for high-volume domains. A single HTTPS endpoint can receive reports from thousands of senders without consuming mailbox storage.

[^failure-detail-optional]: The `failure-details` section is optional. Some sending servers omit it for privacy or operational reasons. The `summary` section is always present and gives the total count of successful and failed sessions.

[rfc-8460]: https://www.rfc-editor.org/info/rfc8460/
