# Django's humanize filters
import datetime

from django.contrib.humanize.templatetags import humanize
from django.template import loader
from django.template.defaulttags import register
from django.utils import timezone, formats

from .. import utils

register.filter(is_safe=True)(humanize.ordinal)
register.filter(is_safe=True)(humanize.intcomma)
register.filter(is_safe=True)(humanize.intword)
register.filter(is_safe=True)(humanize.apnumber)


@register.filter(expects_localtime=True)
def naturalday(value):
    if value and value.year != timezone.now().year:
        return f"{humanize.naturalday(value, 'DATE_FORMAT')}"
    return humanize.naturalday(value, "SHORT_DATE_FORMAT")


@register.filter(expects_localtime=True)
def naturaltime(value: datetime.datetime):
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


@register.simple_tag
def include_md(template_name, **context):
    return utils.md_2_html(loader.get_template(template_name).render(context=context))


@register.simple_tag
def include_md_toc(template_name, depth=None, **context):
    return utils.md_toc(
        loader.get_template(template_name).render(context=context),
        depth=depth,
    )
