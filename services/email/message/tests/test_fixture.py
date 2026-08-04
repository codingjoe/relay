import pytest
from django.core.management import call_command


class TestFixtureLoads:
    @pytest.mark.django_db
    def test_fixture__loads_without_error(self):
        call_command("loaddata", "fixtures/initial_data.yaml", verbosity=0)
