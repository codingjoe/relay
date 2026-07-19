from django.test import RequestFactory, override_settings

from root.views import HomeView


class TestHomeView:
    @override_settings(ALLOWED_HOSTS=["my.platform.com", "localhost", "localhost:8000"])
    def test_get_context_data__nameservers_from_host(self):
        view = HomeView()
        view.request = RequestFactory().get("/", HTTP_HOST="my.platform.com")
        context = view.get_context_data()
        assert context["nameservers"] == ["ns1.my.platform.com", "ns2.my.platform.com"]

    @override_settings(ALLOWED_HOSTS=["localhost", "localhost:8000"])
    def test_get_context_data__strips_port_from_host(self):
        view = HomeView()
        view.request = RequestFactory().get("/", HTTP_HOST="localhost:8000")
        context = view.get_context_data()
        assert context["nameservers"] == ["ns1.localhost", "ns2.localhost"]
