from django.http import HttpResponse
from django.urls import reverse

from root.middleware import PrivateByDefaultMiddleware


class TestPrivateByDefaultMiddleware:
    def test_call__sets_no_store_without_a_cache_control(self, rf):
        middleware = PrivateByDefaultMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(rf.get("/admin/login/"))

        assert response.headers["Cache-Control"] == "private, no-store"

    def test_call__keeps_an_explicit_cache_control(self, rf):
        middleware = PrivateByDefaultMiddleware(
            lambda request: HttpResponse("ok", headers={"Cache-Control": "public"})
        )

        response = middleware(rf.get("/"))

        assert response.headers["Cache-Control"] == "public"

    def test_get__keeps_the_admin_no_cache(self, client):
        response = client.get("/admin/login/")

        assert response.status_code == 200
        assert "no-store" in response.headers["Cache-Control"]

    def test_get__no_store_for_a_missing_page(self, client):
        response = client.get("/does-not-exist/")

        assert response.status_code == 404
        assert response.headers["Cache-Control"] == "private, no-store"

    def test_get__keeps_the_public_page_cache(self, client):
        response = client.get(reverse("home"))

        assert response.headers["Cache-Control"] == "public, max-age=60"
