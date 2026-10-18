---
name: Feedback-ID
description: Grouping Gmail complaint data by stream in Postmaster Tools
author: Johannes Maron
---

# Feedback-ID

> **TL;DR**: Gmail groups complaint rates by the identifiers in the
> `Feedback-ID` header. Send the same identifiers for every message of a
> stream. Then verify your sending domain in Google Postmaster Tools to read
> the rates.

## What the header is for

Recipients report spam. Most mailbox providers then send a complaint report to
the sender, in the [ARF][rfc-5965] format. That report carries the envelope
sender of the reported message. As a result, one complaint maps to one
message.

Gmail does not send those reports. It protects the privacy of the reporter.
A report never includes the recipient address or the message id. Gmail
publishes aggregate complaint rates instead, grouped by the identifiers that
a sender puts in the `Feedback-ID` header. Those rates appear in the
Postmaster Tools FBL dashboard.

## Format

```text
Feedback-ID: a:b:c:SenderId
```

- `a`, `b` and `c` are optional identifiers. Use up to three of them.
- `SenderId` is mandatory. Choose 5 to 15 characters.

Gmail aggregates each identifier separately, so two rules apply:

- The SenderId stays the same for every message of a stream. The optional
  identifiers can vary, for example per campaign or per customer.
- Gmail reports an identifier only when it appears in many messages. A message
  id or a random token appears in one message, so Gmail never reports it.

Gmail reads the first four fields of the header, counted from the right side.
It aggregates each field separately. Therefore the SenderId must be the last
field. A header with more than four fields pushes a value out of the reported
window.

## Requirements

- Add the header before you sign the message. Then the signature covers the
  header.
- Verify the signing domain in Google Postmaster Tools. Google reports
  complaint data for the domain that you verified.
- Send one `Feedback-ID` header per message. A second header makes the group
  ambiguous.
- Keep the SPF record and the PTR record of the sending IPs valid. The reports
  cover authenticated traffic.

The SenderId and the identifiers need no registration.

## Which provider reports what

| Provider                      | How it reports          | Level                                |
| ----------------------------- | ----------------------- | ------------------------------------ |
| Gmail                         | Google Postmaster Tools | Aggregate per identifier and per day |
| Yahoo, AOL, Microsoft, others | ARF report email        | One report per complaint             |

Neither channel includes the recipient address. You cannot reply to a
complaint report. If a recipient asks you to stop, suppress the address in
your own records. A rising complaint rate is a content problem.

[rfc-5965]: https://www.rfc-editor.org/info/rfc5965/
