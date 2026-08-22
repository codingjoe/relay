# Relay: B2B SaaS Communication Platform

A B2B SaaS communication platform for AI applications.
The platform has a **built-in authoritative nameserver**
that removes manual DNS configuration.

## How It Works

Users only need to set **two DNS records**:

1. **NS delegation**. Delegate the sender subdomain to our nameservers
1. **DMARC record**. On the root domain

Everything else (MX, SPF, DKIM, Return-Path) is **served automatically**
by the built-in nameserver. You do not need to use the DNS provider dashboard.

## Managed Sender Domain

Every organization gets a **managed sender domain**. It is a subdomain of the
platform domain, and relay manages it automatically. The domain is
derived from the platform domain as `open.{RELAY_PLATFORM_DOMAIN}` (for
example `open.localhost` in development).
When an organization is created, a `Domain` is auto-created with the name
`{org.slug}.{RELAY_MANAGED_SENDER_DOMAIN}` (for example `acme.open.localhost`).
The domain is DKIM-signed and pre-verified. No user DNS configuration needed.

The managed domain cannot be deleted from the dashboard. Users can still add
their own delegated domains alongside it.

### Operator setup

The platform operator must set up the following records on the
`RELAY_PLATFORM_DOMAIN` nameserver:

1. **NS delegation for `open.{platform_domain}`**. Add NS records for the
   `open` subdomain pointing to `RELAY_DNS_NS_NAMESERVERS` (for example,
   `ns1.{platform_domain}`, `ns2.{platform_domain}`).
1. **A/AAAA record for the web server**. The platform domain itself needs
   an A/AAAA record for the web UI.
1. **Forward DNS for the SMTP server**. Set `RELAY_DNS_SMTP_IPS`. The
   public hostname (`smtp.{platform_domain}`) and sender subdomains resolve
   to the SMTP server IPs.
1. **Reverse DNS for every SMTP server IP**. Configure each IP owner's PTR
   record with the hosting provider. Outbound SMTP must use the corresponding
   hostname for EHLO.
1. **SPF include**. The `spf.{platform_domain}` TXT record must list the
   SMTP server IP addresses.
1. **DMARC**. `_dmarc.{platform_domain}` TXT record.
1. **MTA-STS**. `_mta-sts.{platform_domain}` TXT record and
   `mta-sts.{platform_domain}` CNAME.
1. **TLS-RPT**. `_smtp._tls.{platform_domain}` TXT record.

All per-org records (MX, SPF, DKIM, DMARC, TLS-RPT, MTA-STS) for managed
domains are served automatically by the internal nameserver. No
per-domain delegation is necessary.

## Architecture

```
Organization → Domain, SmtpCredential
```

- **Organization**: Owns resources (domains, credentials). Each user gets a personal org on signup.
- **Domain**: Root domain verified once with NS delegation + DMARC. Holds shared DKIM keys.
- **SendingDomain**: Envelope-from domain (for example, acme.com or app.acme.com) with SPF + DKIM CNAME. Shares the root domain's NS delegation.
- **ReceivingDomain**: Receiving domain with MX record pointing to the root domain's sender subdomain
- **SmtpCredential**: Per-org API key used to authenticate outgoing SMTP submissions
- **Webhook**: Per-org HTTPS endpoint with Ed25519 keypair for signing incoming-mail deliveries
- **DmarcReport**: Aggregate DMARC report (RUA) received from external organizations, parsed from XML
- **DmarcFailureReport**: Forensic DMARC report (RUF) received from external organizations, parsed from ARF
- **FblReport**: Feedback Loop complaint report received from email providers, parsed from ARF (RFC 5965)
- **TlsReport**: TLS-RPT report received from external organizations, parsed from JSON via DRF serializers

All report models use multi-table inheritance with `IncomingMessage` so they
inherit the UUIDv7 primary key and inbound email metadata.

### Services

| Service | Port         | Description                                      |
| ------- | ------------ | ------------------------------------------------ |
| Web     | 8000         | Django web UI (Granian)                          |
| dnsdist | 53 (UDP+TCP) | DNS proxy with caching (production)              |
| DNS     | 5353         | Authoritative nameserver (dnslib, internal only) |
| SMTP    | 587, 465     | Outgoing SMTP submissions (aiosmtpd, TLS direct) |
| MX      | 25           | Incoming MX delivery (aiosmtpd, STARTTLS direct) |
| rspamd  | 11334        | Spam detection (internal only)                   |
| Worker  | N/A          | Threadmill task worker                           |

```mermaid
flowchart TD
    subgraph internet[Internet]
        client[SMTP clients]
        sender[Remote MTAs]
        browser[Browsers]
    end

    subgraph caddy[Caddy reverse proxy + TLS]
        caddy_proxy[Caddy docker-proxy]
    end

    subgraph app[app network]
        web[Web Django + Granian :8000]
        msa[SMTP aiosmtpd :587 :465]
        mta[MX aiosmtpd :25]
        worker[Worker Threadmill]
        rspamd[rspamd :11334]
        minio[MinIO S3 :9000]
    end

    subgraph data[data services]
        pg[PostgreSQL 18+]
        redis[Redis]
    end

    subgraph dns[dnsdist network]
        dnsdist[dnsdist :53 UDP+TCP]
        dns_ns[DNS dnslib :5353]
    end

    browser --> caddy_proxy
    caddy_proxy --> web
    client -->|STARTTLS :587 / TLS :465| msa
    sender -->|STARTTLS :25| mta
    msa --> rspamd
    mta --> rspamd
    rspamd --> redis
    web --> pg
    web --> redis
    web --> minio
    msa --> pg
    msa --> minio
    mta --> pg
    mta --> minio
    dnsdist --> dns_ns
    sender -->|DNS :53| dnsdist
```

The MX server receives incoming email (port 25, STARTTLS by default) and
dispatches it to configurable per-organization webhooks. Clients configure
receiving domains (for example, `app.acme.com`) by pointing an MX record to their
sender subdomain (for example, `MX app.acme.com → mail.relay.acme.com`). Webhooks
follow the [Standard Webhooks](https://standardwebhooks.com) specification -
each delivery includes `webhook-id`, `webhook-timestamp`, and
`webhook-signature` headers with an Ed25519 (`v1a`) signature. Each webhook
has its own keypair, so clients verify with the webhook's public key
(`whpk_` format) using any Standard Webhooks SDK. The payload is flat event
data with a storage URL for the raw message body. The payload never includes
the raw body inline. You can filter webhooks by receiving domain and recipient
address glob pattern.

### Tech Stack

- **Django** with the task framework for async message delivery
- **PostgreSQL**. Primary database
- **Redis**. Caching and rate limiting
- **S3**. Raw message body storage via django-storages
- **basecoat CSS**. Component-based CSS framework for the web UI
- **Granian**: Rust-based ASGI server

### Error monitoring (Sentry)

All five processes report to a single Sentry project. Off by default; set
`SENTRY_DSN` to enable. PII (email bodies, tokens, credentials) is never
sent automatically.

| Variable                    | Default        | Description                                |
| --------------------------- | -------------- | ------------------------------------------ |
| `SENTRY_DSN`                | _(empty: off)_ | Project DSN. Required to enable reporting. |
| `SENTRY_ENVIRONMENT`        | `production`   | Sentry environment tag.                    |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0`          | Tracing sample rate (0-1). Off by default. |

## App dependencies

The graph shows a simplified representation of the app's dependencies.
App dependencies must exist only in a single direction.
Apps can access their parents or grandparents, but not their children.

We have different types of apps:

- **abstract**: Abstract apps are not used directly. Other apps extend them.
- **platform**: Shared infrastructure used across all communication services (email now, VoIP and more later).
- **services**: Specific communication services. Email today, with VoIP and more planned.

```mermaid
graph BT
 abstract[abstract];
 kms[kms];
 subgraph platform
 direction BT
 accounts
 domains
 know_how[know_how]
 alternative_to[alternative_to]
 legal
 well_known[well_known]
 domains --> accounts
 accounts --> abstract
 domains --> kms
 legal --> abstract
 know_how --> abstract
 alternative_to --> abstract
 well_known --> know_how
 well_known --> alternative_to
 end
 subgraph services
 direction BT
 subgraph email
 direction BT
 dashboard[dashboard]
 message[message]
 msa
 mta
 dmarc
 reputation
 message --> accounts
 message --> domains
 msa --> message
 msa --> accounts
 msa --> domains
 msa --> kms
 mta --> message
 mta --> accounts
 mta --> domains
 mta --> kms
 dmarc --> accounts
 dmarc --> domains
 dmarc --> mta
 reputation --> mta
 reputation --> message
 reputation --> domains
 reputation --> accounts
 reputation --> msa
 dashboard --> message
 dashboard --> msa
 dashboard --> mta
 dashboard --> dmarc
 dashboard --> reputation
 end
 subgraph voip
 direction BT
 end
 end
 services --> platform;
 platform --> abstract;
 root --> services;
 root --> platform;
 root(((root)))
```
