import pytest
from django.contrib.auth.models import User

from accounts.models import Membership, Organization


@pytest.fixture(name="db")
def _db(request, db):
    """Test if the test was marked for DB usage."""
    if not request.node.get_closest_marker("django_db"):
        pytest.fail("Test requires a database. Use the django_db marker.")
    yield db


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
