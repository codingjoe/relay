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
    def test__returns_options_response_without_render(self, client, org):
        Domain.objects.create(name="example.com", org=org)

        response = client.options(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )

        assert response.status_code == 200
        assert "OPTIONS" in response["Allow"]

    @pytest.mark.django_db
    def test__passes_through_for_non_mta_sts_path(self, client, settings, org):
        settings.ALLOWED_HOSTS = ["mta-sts.example.com"]
        Domain.objects.create(name="example.com", org=org)
        response = client.get("/", HTTP_HOST="mta-sts.example.com")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test__policy_path_passes_through_for_other_host(self, client, settings, org):
        settings.ALLOWED_HOSTS = ["example.com"]
        Domain.objects.create(name="example.com", org=org)
        response = client.get("/.well-known/mta-sts.txt", HTTP_HOST="example.com")
        assert response.status_code == 404

    @pytest.mark.django_db
    def test__bypasses_allowed_hosts_for_mta_sts(self, client, settings, org):
        settings.ALLOWED_HOSTS = ["localhost"]
        Domain.objects.create(name="example.com", org=org)
        response = client.get(
            "/.well-known/mta-sts.txt", HTTP_HOST="mta-sts.example.com"
        )
        assert response.status_code == 200
        assert "version: STSv1" in response.content.decode()

    @pytest.mark.django_db
    def test__authorizes_registered_domain_before_allowed_hosts(
        self, client, settings, org
    ):
        settings.ALLOWED_HOSTS = ["localhost"]
        Domain.objects.create(name="example.com", org=org)

        response = client.get(
            "/internal/mta-sts/authorize/",
            {"domain": "mta-sts.example.com"},
            HTTP_HOST="web:8000",
        )

        assert response.status_code == 200

    @pytest.mark.django_db
    def test__denies_unknown_domain_before_allowed_hosts(self, client, settings):
        settings.ALLOWED_HOSTS = ["localhost"]

        response = client.get(
            "/internal/mta-sts/authorize/",
            {"domain": "mta-sts.unknown.com"},
            HTTP_HOST="web:8000",
        )

        assert response.status_code == 403

    def test__passes_through_authorize_path_for_allowed_host(self, client, settings):
        settings.ALLOWED_HOSTS = ["localhost"]

        response = client.get(
            "/internal/mta-sts/authorize/",
            {"domain": "mta-sts.example.com"},
            HTTP_HOST="localhost",
        )

        assert response.status_code == 404

    def test__allowed_hosts_blocks_non_mta_sts_path(self, client, settings):
        settings.ALLOWED_HOSTS = ["localhost"]
        response = client.get("/", HTTP_HOST="mta-sts.example.com")
        assert response.status_code == 400
