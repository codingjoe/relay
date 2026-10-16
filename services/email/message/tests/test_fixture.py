import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command


class TestFixtureLoads:
    @pytest.mark.django_db
    def test_fixture__loads_without_error(self):
        call_command("loaddata", "fixtures/initial_data.yaml", verbosity=0)

    @pytest.mark.django_db
    def test_fixture__test_user_is_a_superuser(self):
        call_command("loaddata", "fixtures/initial_data.yaml", verbosity=0)

        user = get_user_model().objects.get(username="test")

        assert user.is_superuser
        assert user.is_staff
