import datetime
import re
import zoneinfo
from types import SimpleNamespace

from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.template import Context, engines
from django.test import RequestFactory
from django.utils import timezone

from .. import abstract


def authenticate(request, *, staff=True, accessed=True):
    request.user = User(is_staff=staff)
    request.session = SimpleNamespace(accessed=accessed)
    return request


def test_admin_url__change_page():
    context = Context({"object": Group(pk=1)})
    context.request = authenticate(RequestFactory().get("/"))
    assert abstract.admin_url(context) == "/admin/auth/group/1/change/"


def test_admin_url__changelist():
    context = Context({"object_list": Group.objects.none()})
    context.request = authenticate(RequestFactory().get("/"))
    assert abstract.admin_url(context) == "/admin/auth/group/"


def test_admin_url__admin_index():
    context = Context()
    context.request = authenticate(RequestFactory().get("/"))
    assert abstract.admin_url(context) == "/admin/"


def test_admin_url__non_staff():
    context = Context({"object": Group(pk=1)})
    context.request = authenticate(RequestFactory().get("/"), staff=False)
    assert abstract.admin_url(context) == ""


def test_admin_url__session_not_accessed():
    context = Context({"object": Group(pk=1)})
    context.request = authenticate(RequestFactory().get("/"), accessed=False)
    assert abstract.admin_url(context) == ""


def test_pagination__multiple_pages():
    """The pagination tag renders filter-preserving links once a second page exists."""
    request = RequestFactory().get("/messages/", {"direction": "sent"})
    template = engines["django"].from_string("{% load abstract %}{% pagination %}")
    html = template.render({"page_obj": Paginator(range(120), 50).page(2)}, request)
    assert "direction=sent&amp;page=1" in html
    assert "direction=sent&amp;page=3" in html


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
        abstract.naturaltime(
            (timezone.localtime() + datetime.timedelta(days=1)).replace(
                hour=8, minute=0
            )
        )
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


def test_human_duration__milliseconds():
    duration = datetime.timedelta(milliseconds=300)

    assert abstract.human_duration(duration) == "300 milliseconds"


def test_human_duration__seconds():
    assert abstract.human_duration(datetime.timedelta(seconds=5)) == "5 seconds"


def test_human_duration__minutes():
    assert abstract.human_duration(datetime.timedelta(seconds=125)) == "2 minutes"


def test_human_duration__whole_minutes():
    assert abstract.human_duration(datetime.timedelta(minutes=1)) == "a minute"


def test_human_duration__hours():
    assert abstract.human_duration(datetime.timedelta(hours=3)) == "3 hours"


def test_apex_suffix__relative_name():
    assert (
        abstract.apex_suffix("mail.relay.acme.com", SimpleNamespace(name="acme.com"))
        == ".acme.com"
    )


def test_apex_suffix__at_the_apex():
    assert abstract.apex_suffix("acme.com", SimpleNamespace(name="acme.com")) == ""


def test_apex_suffix__unrelated_name():
    assert abstract.apex_suffix("example.net", SimpleNamespace(name="acme.com")) == ""


def test_tabler():
    """Render the sprite reference with the default size."""
    template = engines["django"].from_string(
        "{% load abstract %}{% tabler name='copy' %}"
    )
    html = template.render({})
    assert "\n" not in html
    assert 'class="tabler size-4"' in html
    assert 'aria-hidden="true"' in html
    assert "#tabler-copy" in html


def test_tabler__size_and_class():
    """Compose the size class and the extra utilities from the arguments."""
    template = engines["django"].from_string(
        "{% load abstract %}{% tabler name='circle-check' size='3.5'"
        " class='text-primary shrink-0' data_rtl_flip=True %}"
    )
    html = template.render({})
    assert 'class="tabler size-3.5 text-primary shrink-0"' in html
    assert re.search(r"data-rtl-flip(?!=\")", html)
    assert "#tabler-circle-check" in html


def test_tabler__without_size():
    """Render an icon without a size class when size is None."""
    template = engines["django"].from_string(
        "{% load abstract %}{% tabler name='search' size=None %}"
    )
    html = template.render({})
    assert 'class="tabler"' in html
    assert "#tabler-search" in html


def test_timestamp__renders_in_the_current_time_zone():
    value = datetime.datetime(2025, 6, 1, 22, 30, tzinfo=datetime.UTC)

    with timezone.override("Europe/Berlin"):
        data = abstract.timestamp(value)

    assert data["iso"] == "2025-06-02T00:30:00+02:00"
    assert data["natural"] == "June 2, 2025 12:30 a.m."
