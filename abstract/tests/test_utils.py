from django.utils import timezone

from abstract import utils


def test_future():
    assert utils.future() > timezone.now()


def test_future__min_offset():
    now = timezone.now()
    assert utils.future(now=now, min_offset=999) == now + timezone.timedelta(999)


def test_future__max_offset():
    now = timezone.now()
    assert utils.future(now=now, max_offset=1) == now + timezone.timedelta(1)


def test_past():
    assert utils.past() < timezone.now()


def test_md_2_html():
    assert utils.md_2_html("How much is the fish?") == "<p>How much is the fish?</p>"


def test_md_toc():
    assert utils.md_toc("# Level 1\n## Level 2\n###Level 3") == (
        '<div class="toc">\n'
        "<ul>\n"
        '<li><a href="#level-1">Level 1</a><ul>\n'
        '<li><a href="#level-2">Level 2</a><ul>\n'
        '<li><a href="#level-3">Level 3</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</div>\n"
    )


def test_md_toc__depth():
    assert utils.md_toc("# Level 1\n## Level 2\n###Level 3", depth=2) == (
        '<div class="toc">\n'
        "<ul>\n"
        '<li><a href="#level-1">Level 1</a><ul>\n'
        '<li><a href="#level-2">Level 2</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</div>\n"
    )


def test_md_toc__plain_depth():
    assert utils.md_toc(
        "# Level 1\n## Level 2\n### Level 3",
        depth=2,
    ) == (
        '<div class="toc">\n'
        "<ul>\n"
        '<li><a href="#level-1">Level 1</a><ul>\n'
        '<li><a href="#level-2">Level 2</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</div>\n"
    )


def test_md_2_html__fenced_code():
    backticks = "`" * 3
    markdown = f"{backticks}python\nprint('hello')\n{backticks}"
    html = utils.md_2_html(markdown)
    assert '<div class="codehilite">' in html
    assert "<pre>" in html
