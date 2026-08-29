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
