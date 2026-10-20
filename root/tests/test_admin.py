import pytest
from django.urls import reverse


class TestAdminSite:
    @pytest.mark.django_db
    def test_get__index_renders(self, client, admin_user):
        client.force_login(admin_user)
        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        assert "/static/admin/" in response.content.decode()
        assert "/static/css/app.css" in response.content.decode()

    @pytest.mark.django_db
    def test_get__login_uses_stock_widgets(self, client):
        response = client.get(reverse("admin:login"))
        content = response.content.decode()

        assert response.status_code == 200
        assert 'class="input"' not in content
        assert "input-group" not in content
