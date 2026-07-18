"""Models for the nameserver app.

No separate DNS zone model is needed — the Domain model already holds
all DNS-related state (verification, status fields, DKIM keys)."""
