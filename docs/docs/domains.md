---
name: Managed domains and DNS
description: The built-in nameserver, managed sender domains, and verifying delegated domains
author: Johannes Maron
---

# Managed domains and DNS

Most email providers hand you a list of DNS records and hope you type them
correctly. relay ships its own authoritative nameserver. You prove ownership
of your domain once, and the nameserver serves the rest: MX, SPF, DKIM, DMARC
reporting addresses, MTA-STS, TLS-RPT, and the Return-Path zone. This page
explains the domain model, what relay serves in what name, and how
verification works.

## The domain model

| Kind                  | Example               | Who creates it   | Purpose                                                   |
| --------------------- | --------------------- | ---------------- | --------------------------------------------------------- |
| Platform domain       | `relays.to`           | The operator     | The relay infrastructure zone: MX, SMTP, and policy hosts |
| Managed sender domain | `acme.open.relays.to` | relay, at signup | Delegate with zero setup, pre-verified                    |
| Your root domain      | `acme.com`            | You              | Your own domain for From, envelope, and reporting         |
| Sending subdomain     | `mail.relay.acme.com` | relay, derived   | The envelope and DKIM zone. NS delegation points here     |
| Receiving domain      | `app.acme.com`        | You, as domain   | MX record points at the relay MX hostnames                |

In the examples, `acme.com` is your domain and `relays.to` is the relay
platform domain.

Facts to understand about this model:

- **The sender subdomain exists once per root domain.** The envelope
  addresses, the DKIM zone, and the report collectors live under
  `{prefix}.{root}`. You delegate exactly that subdomain to the relay
  nameservers, and you add one DMARC record at your root.
- **Every root domain gets its own signing keys**: RSA-2048 and Ed25519
  keys, one selector each, at `relay-rsa2048` and `relay-ed25519` under
  `_domainkey`. Your domain signs with its own keys, so
  reputation attaches to your domain and not to someone else's.
- **Managed domains cannot be deleted** in the dashboard, and custom domains can.
- There can be no overlap: you cannot register a subdomain of the managed
  domain, and no two organizations can claim overlapping names.

## From signup to first send

```mermaid
flowchart TD
    A[Sign up with GitHub] --> B[Organization created]
    B --> C[Managed sender domain created and verified]
    C --> D[DKIM keys generated for the domain]
    D --> E[Create SMTP credential]
    E --> F[Send immediately]
```

Nothing in this path touches DNS configuration. The nameserver serves the
zone, the platform signs, and you send.

The platform signature comes from a platform domain row registered for the
operator's organization. Relay matches that platform domain by its name.
Once the platform domain exists, the nameserver serves its DKIM selectors
through the ordinary record path, and relay cosigns customer mail. Until
then, relay signs with the sending domain only.

## Adding your own domain

The flow for a user domain, for example `acme.com`:

```mermaid
flowchart TD
    A[Add domain in dashboard] --> B[Store DKIM keys at creation]
    B --> C[Dashboard shows the records to publish]
    C --> D[You publish NS records for the sender subdomain and one DMARC record]
    D --> E[Run verification]
    E --> F{Checks ok?}
    F -- No --> G[Fix shown record, check again]
    G --> E
    F -- Yes --> H[Verified for sending, receiving, or reporting]
    H --> I[Nameserver serves the DNS now]
```

Verification reads the live DNS and groups the result into a service
prerequisite and three tabs:

- Delegation: NS delegation on the sender subdomain. The domain page shows
  the nameservers above the tabs. Sending and reporting both depend on it,
  because the SPF include, the DKIM CNAME targets, and the DMARC and TLS-RPT
  reporting addresses live in that subdomain.
- Sending: SPF authorization and the two DKIM CNAMEs. The Ed25519 record is
  hardening.
- Receiving: the MX record at the root.
- Reporting: the DMARC record with relay reporting addresses, the MTA-STS
  TXT and CNAME records with live MX hosts matching the policy, and the
  TLS-RPT record with the relay reporting address.

The delegation check counts toward both sending and reporting readiness.
Publish the delegation and the sending records and the domain shows sending
verified while receiving and reporting still need setup. Checks run per
record, and the dashboard shows each of them, so a wrong record is
identifiable. Re-check at any time.

## What the nameserver serves

For a delegated domain the authoritative nameserver answers:

| Query name (for acme.com)                 | Type  | Value served                                       |
| ----------------------------------------- | ----- | -------------------------------------------------- |
| `acme.com`                                | MX    | `mx1.relays.to` and `mx2.relays.to`, preference 10 |
| `mail.relay.acme.com`                     | TXT   | SPF record authorizing each relay sending IP       |
| `a.relay-acme._domainkey...` (both zones) | TXT   | DKIM public keys, one per algorithm                |
| `acme.com`                                | TXT   | root SPF include of the sender subdomain           |
| `_dmarc.acme.com`                         | TXT   | DMARC with relay reporting addresses               |
| `_dmarc.mail.relay.acme.com`              | TXT   | per-subdomain DMARC record                         |
| `_mta-sts.acme.com`                       | TXT   | `v=STSv1` policy id                                |
| `mta-sts.acme.com`                        | CNAME | `mta-sts.mail.relay.acme.com`                      |
| `_smtp._tls...`                           | TXT   | TLS-RPT with the relay collector                   |
| `mail.relay.acme.com`                     | NS    | the relay nameservers                              |

The dashboard always shows the current record set with concrete names and
the check state per record, so you never hand-edit names here.

The MTA-STS CNAME points at `mta-sts.mail.relay.acme.com`. That name sits
in the sender subdomain `mail.relay.acme.com`, which the relay nameserver
already serves. relay serves the policy over HTTPS and issues the
certificate for `mta-sts.acme.com` on the first fetch. You add no record
and no certificate for that name.

The policy lists the MX record hostnames by default. If the domain receives
mail through another provider, edit the MTA-STS MX hosts on the domain page.
Enter one host per line. RFC 8461 wildcard patterns such as `*.example.com`
are allowed. An empty field follows the MX record hostnames. Verification
fails when a live MX record does not match one of the listed hosts.

## Receiving-domain notes

A domain can send and receive independently of each other. `app.acme.com` as
a receiving domain needs only its MX record to point at your sender
subdomain. Verification reflects this split: a setup without receiving
records reads as not set up, not as a failure. Read the
<a href="{% url 'docs:detail' slug='receiving' %}">receiving</a> page for
the acceptance flow.

## Troubleshooting

| Symptom                                             | Likely cause                                              | Fix                                                           |
| --------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------- |
| NS check fails                                      | Delegation missing or typo in the NS records              | Publish the NS records from the dashboard instruction         |
| DKIM CNAME check fails                              | CNAME not published yet or typo                           | Copy the selector names exactly                               |
| DMARC check fails                                   | No `v=DMARC1` at the root, or missing relay `rua`/`ruf`   | Publish the shown record with both reporting addresses        |
| MTA-STS check fails                                 | TXT or CNAME wrong, or an MX record is outside the policy | Publish both records and list the live MX hosts in the policy |
| TXT merge needed                                    | Multiple TXT entries at the same name                     | One entry per value, quoted as shown                          |
| Verification stays pending shortly after publishing | DNS caching                                               | Check again after the TTL of your zone                        |

## Related pages

- <a href="{% url 'docs:detail' slug='encryption' %}">Encryption</a>. The
  MTA-STS policy served for your domains.
- <a href="{% url 'docs:detail' slug='webhooks' %}">Webhooks</a>. Receiving
  setup from the application side.
