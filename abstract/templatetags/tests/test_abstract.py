import datetime
import zoneinfo

from django.utils import timezone

from ...utils import future
from .. import abstract


def test_include_md():
    assert (
        abstract.include_md("_testfixtures/include_md.md")
        == "<p>How much is the fish?</p>"
    )


def test_include_md_toc():
    assert abstract.include_md_toc("_testfixtures/toc.md") == (
        '<div class="toc">\n'
        "<ul>\n"
        '<li><a href="#level-1">Level 1</a><ul>\n'
        '<li><a href="#level-2">Level 2</a>'
        "</li>\n"
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</div>\n"
    )


def test_include_md_toc__depth():
    assert abstract.include_md_toc("_testfixtures/toc.md", depth=2) == (
        '<div class="toc">\n'
        "<ul>\n"
        '<li><a href="#level-1">Level 1</a><ul>\n'
        '<li><a href="#level-2">Level 2</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</div>\n"
    )


def test_naturalday():
    assert abstract.naturalday(timezone.localdate()) == "today"
    assert (
        abstract.naturalday(timezone.localdate() - datetime.timedelta(days=1))
        == "yesterday"
    )
    assert (
        abstract.naturalday(timezone.localdate() + datetime.timedelta(days=1))
        == "tomorrow"
    )
    assert abstract.naturalday(datetime.date(2001, 9, 13)) == "Sept. 13, 2001"


def test_naturaltime():
    assert abstract.naturaltime(timezone.now()) == "now"
    assert (
        abstract.naturaltime(timezone.now() - datetime.timedelta(seconds=1))
        == "a second ago"
    )
    assert (
        abstract.naturaltime(timezone.now() - datetime.timedelta(seconds=2))
        == "2 seconds ago"
    )
    assert (
        abstract.naturaltime(timezone.now() - datetime.timedelta(seconds=60))
        == "a minute ago"
    )
    assert (
        abstract.naturaltime(timezone.now() - datetime.timedelta(seconds=60 * 60))
        == "an hour ago"
    )
    assert (
        abstract.naturaltime(timezone.now() - datetime.timedelta(seconds=60 * 60 * 24))
        != "1 day ago"
    )
    assert (
        abstract.naturaltime(
            timezone.datetime(1918, 8, 14, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")),
        )
        == "Aug. 14, 1918 midnight"
    )
    assert (
        abstract.naturaltime(future(max_offset=1).replace(hour=8, minute=0))
        == "tomorrow 8 a.m."
    )


def test_highlight_code__known_language():
    highlighted = abstract.highlight_code('{"key": "value"}', "json")
    assert '<div class="codehilite">' in highlighted
    assert "<pre>" in highlighted


def test_highlight_code__unknown_language():
    highlighted = abstract.highlight_code("plain text", "not-a-language")
    assert '<div class="codehilite">' in highlighted
    assert "<pre>" in highlighted
