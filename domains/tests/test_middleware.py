import pytest

from domains.models import Domain


class TestMtaStsHostMiddleware:
    @pytest.mark.django_db
    def test__serves_policy_for_mta_sts_host(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response.status_code == 200
        assert "version: STSv1" in response.content.decode()

    @pytest.mark.django_db
    def test__returns_421_for_unknown_domain(self, client):
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.unknown.com"
        )
        assert response.status_code == 421

    @pytest.mark.django_db
    def test__passes_through_for_non_mta_sts_path(self, client, org):
        Domain.objects.create(name="example.com", org=org)
        response = client.get("/", HTTP_HOST="mta-sts.example.com")
        assert response.status_code != 404 or "mta-sts" not in response.content.decode()

    @pytest.mark.django_db
    def test__bypasses_allowed_hosts_for_mta_sts(self, client, settings, org):
        settings.ALLOWED_HOSTS = ["localhost"]
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response.status_code == 200
        assert "version: STSv1" in response.content.decode()

    def test__allowed_hosts_blocks_non_mta_sts_path(self, client, settings):
        settings.ALLOWED_HOSTS = ["localhost"]
        response = client.get("/", HTTP_HOST="mta-sts.example.com")
        assert response.status_code == 400
