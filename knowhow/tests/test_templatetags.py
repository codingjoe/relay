from django.template import Context, Template


class TestKnowHowBadge:
    def test_knowhow_badge__renders_link_with_target_blank(self):
        template = Template("{% load knowhow %}{% knowhow_badge 'dmarc' 'DMARC' %}")
        html = template.render(Context({}))
        assert 'href="/know-how/dmarc/"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener"' in html
        assert 'aria-label="DMARC — know how"' in html
        assert 'data-lucide="info"' in html

    def test_knowhow_badge__defaults_label_to_slug(self):
        template = Template("{% load knowhow %}{% knowhow_badge 'spf' %}")
        html = template.render(Context({}))
        assert 'aria-label="spf — know how"' in html
