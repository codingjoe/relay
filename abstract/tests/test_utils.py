from abstract import utils
from django.utils import timezone
import datetime


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


def test_end_of_next_year():
    assert utils.end_of_next_year(datetime.date(2010, 1, 10)) == datetime.date(
        2011,
        12,
        31,
    )
    assert utils.end_of_next_year(datetime.date(2010, 12, 31)) == datetime.date(
        2011,
        12,
        31,
    )
    assert utils.end_of_next_year(datetime.date(2010, 1, 1)) == datetime.date(
        2011,
        12,
        31,
    )
    assert utils.end_of_next_year(datetime.date(2012, 1, 1)) == datetime.date(
        2013,
        12,
        31,
    )


def test_md_2_html():
    assert (
        utils.md_2_html("Peter Piper picked a peck of pickled peppers.")
        == "<p>Peter Piper picked a peck of pickled peppers.</p>"
    )


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
