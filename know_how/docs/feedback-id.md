---
name: Feedback-ID
description: Grouping Gmail complaint data by stream in Postmaster Tools
author: Johannes Maron
---

# Feedback-ID

> **TL;DR**: Gmail groups complaint rates by the identifiers in the
> `Feedback-ID` header. Send the same identifiers for every message of a
> stream, and verify your sending domain in Google Postmaster Tools to read
> them.

## What the header is for

Recipients report spam. Most mailbox providers then send a complaint report to
the sender, in the [ARF][rfc-5965] format. That report echoes the envelope
sender of the message the recipient reported, so one complaint maps to one
message.

Gmail does not send those reports. It protects the privacy of the reporter,
and it never names a single recipient or a single message. Gmail publishes
aggregate complaint rates instead, grouped by the identifiers a sender puts
in the `Feedback-ID` header. Those rates appear in the Postmaster Tools FBL
dashboard.

## Format

```text
Feedback-ID: a:b:c:SenderId
```

- `a`, `b` and `c` are optional identifiers. Use up to three of them.
- `SenderId` is mandatory. Choose 5 to 15 characters.

Two rules come from how Gmail aggregates the values:

- The SenderId stays the same for every message of a stream. The optional
  identifiers may vary, for example per campaign or per customer.
- No value is unique to one message. A message id or a random token never
  appears in enough mail to be reported at all.

Gmail reads the first four fields counted from the right side of the header
and aggregates each one on its own. The SenderId therefore belongs last, and a
header that carries more than four fields pushes a value out of the reported
window.

## Requirements

- Sign the message with DKIM, and add the header before signing, so the
  signature covers it.
- Verify the signing domain in Google Postmaster Tools. Complaint data is
  reported for the verified domain.
- Send one `Feedback-ID` header per message. A second header makes the group
  ambiguous.
- Keep the SPF record and the PTR record of the sending IPs valid. The reports
  cover authenticated traffic.

Nothing else has to be registered. There is no enrollment per identifier and
none per SenderId.

## Which provider reports what

| Provider                      | How it reports          | Level                                |
| ----------------------------- | ----------------------- | ------------------------------------ |
| Gmail                         | Google Postmaster Tools | Aggregate per identifier and per day |
| Yahoo, AOL, Microsoft, others | ARF report email        | One report per complaint             |

Neither channel names the recipient, and neither is a reply you can answer.
Treat a rising complaint rate as a content problem, and suppress the address
from your own records when a recipient asks you to.

[rfc-5965]: https://www.rfc-editor.org/info/rfc5965/
