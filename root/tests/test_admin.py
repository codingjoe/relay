import pytest
from django.urls import reverse


class TestAdminSite:
    @pytest.mark.django_db
    def test_get__index_renders(self, client, admin_user):
        client.force_login(admin_user)
        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        assert "/static/admin/" in response.content.decode()
