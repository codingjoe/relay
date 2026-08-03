import datetime

from django.contrib.humanize.templatetags import humanize
from django.template import loader
from django.template.defaulttags import register
from django.utils import formats, timezone

from .. import utils

register.filter(is_safe=True)(humanize.ordinal)
register.filter(is_safe=True)(humanize.intcomma)
register.filter(is_safe=True)(humanize.intword)
register.filter(is_safe=True)(humanize.apnumber)


@register.filter(expects_localtime=True)
def naturalday(value):
    """Format a date as a human-readable day.

    Use ``SHORT_DATE_FORMAT`` for dates in the current year and
    ``DATE_FORMAT`` for dates in other years.
    """
    if value and value.year != timezone.now().year:
        return f"{humanize.naturalday(value, 'DATE_FORMAT')}"
    return humanize.naturalday(value, "SHORT_DATE_FORMAT")


@register.filter(expects_localtime=True)
def naturaltime(value: datetime.datetime):
    """Format a datetime as a human-readable relative time.

    Switches from a relative format for recent values to absolute
    date and time formats for older values.
    """
    if not isinstance(value, datetime.datetime):
        return value
    now = timezone.now()
    delta = value - now
    if 2 > delta.total_seconds() / 60 / 60 > -2:
        return humanize.naturaltime(value)
    if 2 > delta.days > -2:
        return f"{humanize.naturalday(value, 'SHORT_DATE_FORMAT')} {formats.time_format(value)}"
    if value.year != now.year:
        return (
            f"{formats.date_format(value, 'DATE_FORMAT')} {formats.time_format(value)}"
        )
    return formats.date_format(value, "SHORT_DATETIME_FORMAT")


@register.simple_tag(takes_context=True)
def param_replace(context, **kwargs):
    """Replace query parameters in the current URL.

    Preserve existing GET parameters and override the ones passed as kwargs.
    Remove empty values.
    """
    d = context["request"].GET.copy()
    for k, v in kwargs.items():
        d[k] = v
    for k in [k for k, v in d.items() if not v]:
        del d[k]
    return d.urlencode()


@register.inclusion_tag("abstract/timestamp.html")
def timestamp(value):
    """Render a ``<time>`` element with naturaltime and ISO 8601 tooltip."""
    if not value:
        return {"value": None, "iso": "", "natural": ""}
    return {
        "value": value,
        "iso": value.isoformat(),
        "natural": naturaltime(value),
    }


@register.inclusion_tag("abstract/pagination.html", takes_context=True)
def pagination(context, page_obj=None):
    """Render a pagination nav for a Django Page object.

    Falls back to ``context['page_obj']`` when ``page_obj`` is omitted,
    so most templates can call ``{% pagination %}`` without an argument.
    """
    return {"page_obj": page_obj or context.get("page_obj")}


@register.simple_tag
def include_md(template_name, **context):
    """Render a Markdown template to HTML, stripping any YAML frontmatter."""
    rendered = loader.get_template(template_name).render(context=context)
    return utils.md_2_html(utils.strip_frontmatter(rendered))


@register.simple_tag
def include_md_toc(template_name, depth=None, **context):
    """Render a table of contents for a Markdown template, stripping frontmatter."""
    rendered = loader.get_template(template_name).render(context=context)
    return utils.md_toc(utils.strip_frontmatter(rendered), depth=depth)
