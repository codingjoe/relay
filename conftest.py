import dns.message
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import dns.rrset
import pytest
from django.contrib.auth.models import User
from django.db import connections

from accounts.models import Membership, Organization


@pytest.fixture(name="db")
def _db(request, db):
    """Fail if the requesting test lacks the `django_db` marker."""
    if not request.node.get_closest_marker("django_db"):
        pytest.fail("Test requires a database. Use the django_db marker.")
    return db


@pytest.fixture(autouse=True)
def assert_django_db_used(request, _django_db_marker):
    """Fail if a test carries the `django_db` marker but executes no database queries."""
    if not request.node.get_closest_marker("django_db"):
        yield
        return

    query_count = 0

    def count_query(execute, sql, params, many, context):
        nonlocal query_count
        query_count += 1
        return execute(sql, params, many, context)

    wrappers = [
        connections[alias].execute_wrapper(count_query) for alias in connections
    ]
    for wrapper in wrappers:
        wrapper.__enter__()

    yield

    for wrapper in wrappers:
        wrapper.__exit__(None, None, None)

    if query_count == 0:
        pytest.fail(
            "Test is marked with @pytest.mark.django_db but did not access "
            "the database. Remove the marker."
        )


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="secret",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="secret",
    )


@pytest.fixture
def org(db, user):
    org = Organization.objects.create(
        slug="test-org",
        billing_is_active=True,
    )
    Membership.objects.create(
        org=org,
        user=user,
        role=Membership.Role.ADMIN,
    )
    return org


@pytest.fixture
def write_org(db, other_user):
    org = Organization.objects.create(
        slug="other-org",
        billing_is_active=True,
    )
    Membership.objects.create(
        org=org,
        user=other_user,
        role=Membership.Role.WRITE,
    )
    return org


@pytest.fixture
def admin_client(client, user):
    client.force_login(user)
    return client


class StubResolver(dns.resolver.Resolver):
    """
    Return real DNS Answer objects from pre-configured records.

    Unlike mocking dns.resolver.resolve, this returns real Answer objects
    that exercise the actual parsing logic in service functions.
    """

    def __init__(self):
        super().__init__(configure=False)
        self._records: dict[tuple[str, str], list[str]] = {}
        self._failures: dict[tuple[str, str], Exception] = {}
        self.lookups: list[tuple[str, str]] = []

    def add(self, qname: str, rdtype: str, *rdata_texts: str):
        """Register a DNS record."""
        self._records[(qname.lower(), rdtype.upper())] = list(rdata_texts)

    def fail(self, qname: str, rdtype: str, error: Exception):
        """Raise the given error instead of serving the record."""
        self._failures[(qname.lower(), rdtype.upper())] = error

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
        rdtype_int = dns.rdatatype.from_text(rdtype_str)
        query_name = dns.name.from_text(str(qname))
        owner = query_name
        owner_str = qname_str
        # A recursive resolver chases a CNAME, so the answer RRset is owned by
        # the canonical name and not by the queried name.
        answer_rrsets = []
        visited = {qname_str}

        while True:
            key = (owner_str, rdtype_str)
            self.lookups.append(key)

            if error := self._failures.get(key):
                raise error

            if (rdata_texts := self._records.get(key)) is not None:
                break

            cname_texts = self._records.get((owner_str, "CNAME"))
            if not cname_texts:
                raise dns.resolver.NXDOMAIN(qname)

            cname_rrset = dns.rrset.from_rdata_list(
                owner,
                1800,
                [
                    dns.rdata.from_text(rdclass, dns.rdatatype.CNAME, text)
                    for text in cname_texts
                ],
            )
            answer_rrsets.append(cname_rrset)
            owner = cname_rrset[0].target
            owner_str = str(owner).rstrip(".").lower()
            if owner_str in visited:
                raise dns.resolver.NXDOMAIN(qname)
            visited.add(owner_str)

        if not rdata_texts and raise_on_no_answer:
            raise dns.resolver.NoAnswer()

        if not rdata_texts:
            return None

        answer_rrsets.append(
            dns.rrset.from_rdata_list(
                owner,
                1800,
                [
                    dns.rdata.from_text(rdclass, rdtype_int, text)
                    for text in rdata_texts
                ],
            )
        )

        query = dns.message.make_query(query_name, rdtype_int, rdclass)
        response = dns.message.make_response(query)
        for rrset in answer_rrsets:
            response.answer.append(rrset)
        # Pack and re-parse to rebuild the message index, which find_rrset uses
        response = dns.message.from_wire(response.to_wire())

        return dns.resolver.Answer(query_name, rdtype_int, rdclass, response)


@pytest.fixture
def dns_resolver(monkeypatch):
    """Replace the default DNS resolver with a configurable stub."""
    stub = StubResolver()
    monkeypatch.setattr(dns.resolver, "default_resolver", stub)
    monkeypatch.setattr(dns.resolver, "Resolver", lambda *args, **kwargs: stub)
    return stub
