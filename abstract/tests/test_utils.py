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


def test_md_2_html__mermaid_block():
    fence = 3 * "`"
    html = str(utils.md_2_html(f"{fence}mermaid\nflowchart TD\n  A --> B\n{fence}"))
    assert '<pre class="mermaid">flowchart TD\n  A --&gt; B</pre>' in html
    assert fence not in html


def test_md_2_html__mermaid_block_preserved_in_untouched_fences():
    fence = 3 * "`"
    html = str(utils.md_2_html(f"{fence}python\nprint('hi')\n{fence}"))
    assert "print" in html
    assert 'class="mermaid"' not in html


def test_md_2_html__unclosed_mermaid_block():
    fence = 3 * "`"
    html = str(utils.md_2_html(f"{fence}mermaid\nflowchart TD\n A --> B"))
    assert "flowchart" in html


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
