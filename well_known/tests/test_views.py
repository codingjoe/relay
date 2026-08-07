from django.urls import reverse


class TestRobotsTxt:
    def test_get__returns_robots_txt(self, client):
        response = client.get(reverse("well_known:robots-txt"))
        assert response.status_code == 200
        assert "text/plain" in response["Content-Type"]
        body = response.content.decode()
        assert "User-agent: *" in body
        assert "Sitemap:" in body
        assert "/sitemap.xml" in body


class TestLlmsTxt:
    def test_get__returns_llms_txt(self, client):
        response = client.get(reverse("well_known:llms-txt"))
        assert response.status_code == 200
        assert "text/plain" in response["Content-Type"]
        body = response.content.decode()
        assert body.startswith("# relay")
        assert "> B2B SaaS" in body
        assert "## Know how" in body
        assert "## Legal" in body
        assert "DMARC" in body
        assert "Imprint" in body

    def test_get__contains_article_links(self, client):
        response = client.get(reverse("well_known:llms-txt"))
        body = response.content.decode()
        assert "/know-how/dmarc/" in body
        assert "/know-how/spf/" in body

    def test_get__contains_legal_links(self, client):
        response = client.get(reverse("well_known:llms-txt"))
        body = response.content.decode()
        assert "/legal/imprint/" in body
        assert "/legal/terms/" in body
        assert "/legal/privacy/" in body

    def test_get__contains_alternative_to_section(self, client):
        response = client.get(reverse("well_known:llms-txt"))
        body = response.content.decode()
        assert "## Alternative to" in body
        assert "/alternative-to/ses/" in body
        assert "/alternative-to/sendgrid/" in body


class TestLlmsFullTxt:
    def test_get__returns_full_text(self, client):
        response = client.get(reverse("well_known:llms-full-txt"))
        assert response.status_code == 200
        assert "text/plain" in response["Content-Type"]
        body = response.content.decode()
        assert "relay \u2014 know how (full text)" in body
        assert "DMARC" in body
        assert "SPF" in body

    def test_get__includes_article_content(self, client):
        response = client.get(reverse("well_known:llms-full-txt"))
        body = response.content.decode()
        assert "TL;DR" in body
        assert "RFC 7489" in body

    def test_get__includes_comparison_content(self, client):
        response = client.get(reverse("well_known:llms-full-txt"))
        body = response.content.decode()
        assert "Alternative to Amazon SES" in body
        assert "/alternative-to/ses/" in body


class TestSitemap:
    def test_get__returns_sitemap_xml(self, client):
        response = client.get(reverse("well_known:sitemap"))
        assert response.status_code == 200
        assert "application/xml" in response["Content-Type"]
        body = response.content.decode()
        assert "<urlset" in body
        assert "<url>" in body
        assert "</url>" in body

    def test_get__contains_know_how_articles(self, client):
        response = client.get(reverse("well_known:sitemap"))
        body = response.content.decode()
        assert "/know-how/dmarc/" in body
        assert "/know-how/spf/" in body

    def test_get__contains_legal_pages(self, client):
        response = client.get(reverse("well_known:sitemap"))
        body = response.content.decode()
        assert "/legal/imprint/" in body
        assert "/legal/terms/" in body
        assert "/legal/privacy/" in body

    def test_get__contains_alternative_to_articles(self, client):
        response = client.get(reverse("well_known:sitemap"))
        body = response.content.decode()
        assert "/alternative-to/ses/" in body
        assert "/alternative-to/sendgrid/" in body
