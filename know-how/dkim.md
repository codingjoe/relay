# DKIM

DKIM (DomainKeys Identified Mail) adds a cryptographic signature to each outgoing email. Receiving mail servers verify the signature with the public key from DNS. This proves that the message came from your domain and was not changed in transit.

## How DKIM works

The sending mail server signs the message with a private key. The DNS record for the selector contains the public key. The selector is a label that identifies which key to use. For example, `relay._domainkey.example.com` contains the public key for the relay selector.

## DNS records

DKIM uses TXT records at `<selector>._domainkey.<domain>`. The record starts with `v=DKIM1` and contains the public key in the `p=` tag. relay supports RSA-2048, RSA-1024, and Ed25519 keys.

## How relay uses DKIM

relay generates and stores the private keys for you. relay publishes the public keys as DNS records on the sender subdomain. Each cipher type gets its own selector and CNAME record. You do not need to create or manage DKIM keys.

## DKIM and DMARC

DKIM is one of the two authentication methods that \[DMARC\]({% url 'know_how:detail' slug='dmarc' %}) uses. The other is \[SPF\]({% url 'know_how:detail' slug='spf' %}). DMARC requires at least one of the two to pass.
