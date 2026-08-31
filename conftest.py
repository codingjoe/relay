import pytest
from django.contrib.auth.models import User
from django.db import connections

from accounts.models import Membership, Organization


@pytest.fixture(name="db")
def _db(request, db):
    """Fail if the requesting test lacks the `django_db` marker."""
    if not request.node.get_closest_marker("django_db"):
        pytest.fail("Test requires a database. Use the django_db marker.")
    yield db


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
    org = Organization.objects.create(slug="test-org")
    Membership.objects.create(
        org=org,
        user=user,
        role=Membership.Role.ADMIN,
    )
    return org


@pytest.fixture
def write_org(db, other_user):
    org = Organization.objects.create(slug="other-org")
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
        key = (qname_str, rdtype_str)
        self.lookups.append(key)

        if error := self._failures.get(key):
            raise error

        if (rdata_texts := self._records.get(key)) is None:
            raise dns.resolver.NXDOMAIN(qname)

        if not rdata_texts and raise_on_no_answer:
            raise dns.resolver.NoAnswer()

        if not rdata_texts:
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
def dns_resolver(monkeypatch):
    """Replace the default DNS resolver with a configurable stub."""
    stub = StubResolver()
    monkeypatch.setattr(dns.resolver, "default_resolver", stub)
    monkeypatch.setattr(dns.resolver, "Resolver", lambda *args, **kwargs: stub)
    return stub
