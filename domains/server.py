"""Integrate the authoritative resolver with dnslib's server."""

from django.db import DatabaseError
from dnslib import DNSRecord
from dnslib.dns import RCODE, DNSError

from .resolver import DNSResolver


class DNSReplyResolver:
    """Convert DNS record lookups into dnslib server replies."""

    def __init__(self):
        self.record_resolver = DNSResolver()

    def resolve(self, request: DNSRecord, handler) -> DNSRecord:
        """Return an authoritative DNS reply for a dnslib server request."""
        reply = request.reply(ra=0)

        try:
            reply.add_answer(
                *self.record_resolver.resolve(request.q.qname, request.q.qtype)
            )
        except DNSError, DatabaseError:
            reply.header.rcode = RCODE.SERVFAIL

        return reply
