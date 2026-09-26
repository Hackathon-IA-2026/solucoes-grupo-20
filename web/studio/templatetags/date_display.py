from datetime import date, datetime

from django import template
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.html import format_html


register = template.Library()


def _parse_value(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    return parse_datetime(value) or parse_date(value)


@register.simple_tag
def human_date(value):
    parsed = _parse_value(value)
    if parsed is None:
        return value if value not in (None, '') else '—'

    if isinstance(parsed, datetime):
        if timezone.is_aware(parsed):
            parsed = timezone.localtime(parsed)
        label = parsed.strftime('%d/%m/%Y %H:%M')
        machine_value = parsed.isoformat()
    else:
        label = parsed.strftime('%d/%m/%Y')
        machine_value = parsed.isoformat()

    return format_html('<time datetime="{}">{}</time>', machine_value, label)