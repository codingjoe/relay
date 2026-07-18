# Relay — B2B SaaS Communication Platform

A modern B2B SaaS communication platform built on Django 6.0 and Python 3.14, designed for AI applications,
with a **built-in authoritative nameserver** that eliminates manual DNS configuration.

## How It Works

Users only need to set **two DNS records**:

1. **NS delegation** — Delegate the sender subdomain to our nameservers
1. **DMARC record** — On the root domain

Everything else — MX, SPF, DKIM, Return-Path — is **served automatically**
by the built-in nameserver. No more digging through DNS provider dashboards.

## Free Sender Domain

Every account gets a **free sender domain** it can send from without configuring
any DNS of its own. The domain is set via `RELAY_FREE_SENDER_DOMAIN` (defaults
to `open.{RELAY_PLATFORM_DOMAIN}`, e.g. `open.localhost` in development) and is
backed by a system-owned `Domain` (`owner=None`) that is auto-created by a
migration and DKIM-signed automatically.

The free domain is restricted: messages may only be sent to the user's own
registered email address. Use it to verify deliverability and test integrations
before delegating a real sender domain.

### DNS served automatically

The built-in nameserver serves the following records at the free domain apex.
No user action is required.

| Record | Location                                             | Value                                            |
| ------ | ---------------------------------------------------- | ------------------------------------------------ |
| A      | `open.{platform_domain}`                             | SMTP server IP(s)                                |
| MX     | `open.{platform_domain}`                             | `open.{platform_domain}` (priority 10)           |
| SPF    | `open.{platform_domain}` (TXT)                       | `v=spf1 a mx include:spf.{platform_domain} ~all` |
| DKIM   | `{selector}._domainkey.open.{platform_domain}` (TXT) | DKIM public key                                  |
| DMARC  | `_dmarc.open.{platform_domain}` (TXT)                | `v=DMARC1; p=none`                               |

### Operator setup

For the free domain to resolve in production, the platform operator must:

1. **Delegate the free domain zone to Relay's nameservers.** If
   `RELAY_FREE_SENDER_DOMAIN` is `open.example.com`, add NS records for the
   `open` subdomain pointing to the nameservers in
   `RELAY_DNS_NS_NAMESERVERS` (e.g. `ns1.example.com`, `ns2.example.com`). If
   the platform domain's NS records already point at Relay's nameservers, the
   free domain is served automatically as a subdomain and no extra delegation
   is needed.
1. **Make the SPF include resolve.** The free domain's SPF record includes
   `spf.{platform_domain}`. Ensure that TXT record exists and lists the SMTP
   server IPs.
1. **Set `RELAY_FREE_SENDER_DOMAIN`** to a domain delegated to Relay's
   nameservers.

## Architecture

```
User → Domain
```

- **User** — Authenticated via GitHub OAuth, owns domains and SMTP credentials
- **Domain** — Sender domain with automatic DKIM key generation and DNS serving

### Services

| Service | Port         | Description                        |
| ------- | ------------ | ---------------------------------- |
| Web     | 8000         | Django web UI (Granian)            |
| DNS     | 53 (UDP+TCP) | Authoritative nameserver (dnslib)  |
| SMTP    | 25, 587      | Inbound + outbound SMTP (aiosmtpd) |

### Tech Stack

- **Django 6.0** with the task framework for async message delivery
- **PostgreSQL** — primary database
- **Redis** — caching and rate limiting
- **S3** — raw message body storage via django-storages
- **Primer CSS** — GitHub's design system CSS framework for the web UI
- **Granian** — Rust-based ASGI server

## Getting Started

### Prerequisites

- Python 3.14
- PostgreSQL
- Redis
- Docker (optional, for containerized deployment)

### Local Development

```bash
# Install dependencies
uv sync

# Run migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

### Docker

```bash
# Build and start all services
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate
```

### Environment Variables

| Variable                       | Default                  | Description                                                  |
| ------------------------------ | ------------------------ | ------------------------------------------------------------ |
| `SECRET_KEY`                   | —                        | Django secret key                                            |
| `DEBUG`                        | `False`                  | Debug mode                                                   |
| `DATABASE_URL`                 | `sqlite:///db.sqlite3`   | Database URL                                                 |
| `REDIS_URL`                    | `redis:///`              | Redis URL                                                    |
| `RELAY_PLATFORM_DOMAIN`        | `localhost`              | Platform domain used to derive other domains                 |
| `RELAY_FREE_SENDER_DOMAIN`     | `open.{platform_domain}` | Free sender domain (system-owned, sends to own address only) |
| `RELAY_DNS_NS_NAMESERVERS`     | `ns1,ns2.relay.dev`      | Authoritative nameservers                                    |
| `RELAY_DNS_MX_RECORDS`         | `mx1,mx2.relay.dev`      | MX records to serve                                          |
| `RELAY_DNS_SPF_INCLUDE`        | `spf.relay.dev`          | SPF include target                                           |
| `RELAY_DNS_RETURN_PATH_DOMAIN` | `rp.relay.dev`           | Return-Path CNAME target                                     |
| `RELAY_SMTP_LISTEN_PORT`       | `25`                     | SMTP listen port                                             |
| `RELAY_SMTP_SUBMISSION_PORT`   | `587`                    | SMTP submission port                                         |
| `RELAY_DNS_LISTEN_PORT`        | `53`                     | DNS listen port                                              |
| `GITHUB_CLIENT_ID`             | —                        | GitHub OAuth app client ID                                   |
| `GITHUB_CLIENT_SECRET`         | —                        | GitHub OAuth app client secret                               |

### GitHub OAuth Setup

1. Go to **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App**
1. Set **Authorization callback URL** to `https://<your-domain>/auth/github/callback/`
1. Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in your environment
