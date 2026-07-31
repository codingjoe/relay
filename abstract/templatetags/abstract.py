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
    """Format a date as a human-readable day (for example, "today", "yesterday", "Sep 13").

    Uses `SHORT_DATE_FORMAT` for dates in the current year and
    `DATE_FORMAT` for dates in other years.
    """
    if value and value.year != timezone.now().year:
        return f"{humanize.naturalday(value, 'DATE_FORMAT')}"
    return humanize.naturalday(value, "SHORT_DATE_FORMAT")


@register.filter(expects_localtime=True)
def naturaltime(value: datetime.datetime):
    """Format a datetime as a human-readable relative time.

    Uses Django's `naturaltime` for recent values (within ±2 hours), then
    changes to longer date and time formats for older values.

    Args:
        value: The datetime to format.

    Returns:
        A human-readable time string, or the input unchanged if it is not
        a datetime.
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

    Preserves existing GET parameters and overrides the ones passed as kwargs.
    Empty values are removed.

    Args:
        context: The template context (must contain `request`).
        **kwargs: Query parameters to set or override.

    Returns:
        A URL-encoded query string with the updated parameters.
    """
    d = context["request"].GET.copy()
    for k, v in kwargs.items():
        d[k] = v
    for k in [k for k, v in d.items() if not v]:
        del d[k]
    return d.urlencode()


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
