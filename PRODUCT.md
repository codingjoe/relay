# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Developers building AI agents and AI-driven applications that need to send and
receive email programmatically. They use the dashboard to configure sender
domains, SMTP credentials, and webhooks, and to monitor deliverability and
sender reputation. Their agents consume the product over SMTP, API, or MCP.

## Product Purpose

relay is communication as a service, not just email. Create
an account and you can send an email immediately; VoIP will follow the same
pattern. Email sending, receiving, and reputation monitoring are live today.
Every organization gets a managed sender domain
(`{org}.open.{platform-domain}`) that is pre-verified and DKIM-signed from
signup: zero setup, relay handles the DNS, authentication, and deliverability
plumbing behind the scenes. Pre-launch stage: success means reaching a
trustworthy launch that converts signups into active senders.

## Positioning

relay is a developer-first IT infrastructure provider. It builds superior
products and enables clients to build AAA applications on top of them. Email
is the first product, and its differentiator is simplicity: relay handles the
DNS and email plumbing, so sending and receiving work with near-zero
configuration. AI-native access (MCP alongside SMTP, API, and Standard
Webhooks) serves agents and applications alike. Hosted in the EU, GDPR
compliant, with no third-country data transfer.

## Operating Context

Developer workflow, confirmed from product code and copy:

- Sign up via GitHub OAuth; a personal organization is created automatically.
- A managed sender domain is ready immediately, no DNS work to start.
- Custom domains are added with NS delegation + DMARC only; the dashboard
  verifies and serves the remaining records.
- Send via SMTP submission (ports 587/465) or MCP; receive via MX to
  Standard Webhooks (Ed25519-signed, `whpk_` keys) or MCP.
- Monitor DMARC aggregate (RUA) and forensic (RUF) reports, TLS-RPT, bounce
  rates, and sender reputation per domain.
- Suppression list, message retention (30 days), unlimited domains and team
  members.

## Capabilities and Constraints

- Email sending, receiving, reputation monitoring, dev sandbox (landing-page
  feature set).
- Standard Webhooks deliveries with a flat payload and a storage URL; raw
  bodies are never inlined.
- Multi-organization accounts with memberships; GitHub OAuth is the only
  confirmed auth method.
- Pay-per-relay pricing shown on the landing page: no licenses, seats, or
  subscriptions; you pay when relay relays. The hero claims the product,
  not the price: "Email sending, receiving, monitoring, and sandboxes. So
  good you'll check the dashboard for fun." First 1,000 emails/month
  free, then €0.75 per 1,000; pricing is pre-launch and unvalidated.
- Landing page stage framing: pre-launch/early access. The primary CTA is
  "get early access"; signup currently stays open via GitHub OAuth (the
  invite-only/waitlist framing is copy-only; a real gate and waitlist are
  future work).
- Landing page proof sections: a brand banner ("backed by builders from")
  carrying real, owner-attested endorsements (Henkel, Porsche, Thermondo,
  Fizard, voiio, Sparkasse) fed from `root/views.py` (`BRANDS`), and
  testimonials ("early supporters") still fed from placeholder data
  (`TESTIMONIALS`) pending real quotes; real email-log screenshots
  captured from the product, overview and detail
  (`root/static/img/email-overview.png`,
  `root/static/img/email-detail.png`); a code-example tabs section
  (Django and Next, sending and receiving each, the Django send using
  the `MAILERS` setting); and a "no black box" trust band (SPF, DKIM,
  DMARC, MTA-STS, TLS-RPT, FBL, ARC, Standard Webhooks linked to the
  spec) that carries the open-source pledge as one muted line instead
  of a full-bleed panel.
- VoIP and further communication services are planned; email is the first
  service on the platform.
- Tech constraints that shape UI work: Django templates + basecoat CSS
  (Tailwind), light/dark color scheme, django i18n with bidi support.

## Brand Commitments

None binding except the name casing. Confirmed on 2026-08-28: the name is
"relay", always lowercase, a binding commitment. Everything else visual and
verbal remains open to change; the incumbent voice "made with \<3 and
German engineering" with
monospace accents is evidence of the incumbent look, not a commitment.

## Evidence on Hand

- Landing page copy: `root/templates/start.html` (feature cards, brand
  banner, email-log screenshots, code-example tabs (Django and Next),
  testimonials, trust band, interactive pricing slider, EU/GDPR claims)
  and `root/views.py` (`BRANDS`, `TESTIMONIALS` placeholder data).
- Legal pages: `legal/docs/` (imprint, privacy, terms).
- Architecture documentation: `README.md`; conventions: `CONVENTIONS.md`.
- Test data bundle: `fixtures/initial_data.yaml`.
- No testimonials, case studies, customer logos, benchmarks, or press exist
  beyond the owner-attested brand-banner endorsements (Henkel, Porsche,
  Thermondo, Fizard, voiio, Sparkasse). The testimonials section still ships
  clearly-marked sample entries, which must be replaced with real quotes
  before launch. Future work must not fabricate any of these.

## Product Principles

Developer-first, the overarching principle: every decision serves the
developer building on relay, no marketing fluff.

1. Empowerment through transparency, derived from developer-first: show
   verification, DNS state, and reputation plainly and truthfully, so
   developers can act on what they see.
1. Sovereignty through privacy: message data is processed only to deliver and
   report, never to profile, mine, or resell. EU hosting is an extension of
   this focus, not the story itself.
1. Passion for excellence: craft every detail
   (reliability, clarity, polish) as visible respect for the developers who rely on relay.

## Accessibility & Inclusion

The interface ships light/dark color schemes and is localized via django i18n
with RTL support. The accessibility target follows the
Barrierefreie-Informationstechnik-Verordnung (BITV) 2.0, EU Directive
2016/2102, and the Web Content Accessibility Guidelines (WCAG) 2.0.
