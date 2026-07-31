# PTR

PTR (Pointer record) is a DNS record that maps an IP address back to a hostname. This reverse lookup is the opposite of an A record, which maps a hostname to an IP address.

## How PTR works

A mail server that receives email checks the PTR record of the sending IP address. If the PTR hostname does not match the sending domain, the receiving server may reject or flag the message. Many mail providers use the PTR check as a spam signal.

## DNS format

PTR records live in the `in-addr.arpa` zone for IPv4 and the `ip6.arpa` zone for IPv6. For example, the IP `192.0.2.1` has a PTR record at `1.2.0.192.in-addr.arpa`.

## How relay uses PTR

relay publishes the PTR record for the SMTP server IP address automatically. The record points to the relay mail hostname. You do not need to configure PTR records.
