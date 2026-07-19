import dns.message
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import dns.rrset
import pytest


class StubResolver(dns.resolver.Resolver):
    """Return real DNS Answer objects from pre-configured records.

    Unlike mocking dns.resolver.resolve, this returns real Answer objects
    that exercise the actual parsing logic in service functions.
    """

    def __init__(self):
        super().__init__(configure=False)
        self._records: dict[tuple[str, str], list[str]] = {}

    def add(self, qname: str, rdtype: str, *rdata_texts: str):
        """Register a DNS record."""
        self._records[(qname.lower(), rdtype.upper())] = list(rdata_texts)

    def resolve(
        self,
        qname,
        rdtype=dns.rdatatype.A,
        rdclass=dns.rdataclass.IN,
        tcp=False,
        source=None,
        raise_on_no_answer=True,
        source_port=0,
        lifetime=None,
        search=None,
    ):
        qname_str = str(qname).rstrip(".").lower()
        rdtype_str = (
            dns.rdatatype.to_text(rdtype) if isinstance(rdtype, int) else rdtype.upper()
        )
        key = (qname_str, rdtype_str)

        if key not in self._records:
            raise dns.resolver.NXDOMAIN(qname)

        rdata_texts = self._records[key]
        if not rdata_texts:
            if raise_on_no_answer:
                raise dns.resolver.NoAnswer()
            return None

        qname_obj = dns.name.from_text(str(qname))
        rdtype_int = dns.rdatatype.from_text(rdtype_str)
        rdatas = [
            dns.rdata.from_text(rdclass, rdtype_int, text) for text in rdata_texts
        ]
        rrset = dns.rrset.from_rdata_list(qname_obj, 1800, rdatas)

        query = dns.message.make_query(qname_obj, rdtype_int, rdclass)
        response = dns.message.make_response(query)
        response.answer.append(rrset)
        # Pack and re-parse to rebuild the message index, which find_rrset uses
        response = dns.message.from_wire(response.to_wire())

        return dns.resolver.Answer(qname_obj, rdtype_int, rdclass, response)


@pytest.fixture
def dns_resolver():
    """Replace the default DNS resolver with a configurable stub.

    Returns the stub so tests can add records via ``dns_resolver.add(...)``.
    Uses real dns.resolver.Answer objects — no MagicMock.
    """
    stub = StubResolver()
    original = dns.resolver.default_resolver
    dns.resolver.default_resolver = stub
    try:
        yield stub
    finally:
        dns.resolver.default_resolver = original
